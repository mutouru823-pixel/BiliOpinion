# -*- coding: utf-8 -*-
"""
Step6 BERT 语义向量（可选，默认关闭；需 torch + transformers）

用 chinese-bert-wwm-ext 做 last-hidden-state 平均池化，得到每条评论的句向量。
默认在 CPU 上做 INT8 动态量化以提速。结果保存为 .npy + 映射 csv，供 Step7/8 使用。

注意：向量化全部评论在 CPU 上较慢；可用 cfg.bert.max_samples 限制参与聚类的样本量。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..utils import robust_read_csv, get_logger, banner

log = get_logger()


def run(cfg) -> dict:
    bcfg = cfg["bert"]
    if not bcfg.get("enabled", False):
        log.info("BERT 步骤未启用（cfg.bert.enabled=False），跳过 Step6。")
        return {"stats": {"skipped": True}, "figures": [], "data_files": []}

    try:
        import torch
        from transformers import AutoModel, AutoTokenizer
    except Exception as e:  # noqa: BLE001
        raise RuntimeError("BERT 步骤需要 torch 与 transformers，请先 `pip install torch transformers`：%s" % e)

    out = cfg.dir_data
    banner(f"Step6 BERT 向量化 · {cfg.topic}")

    df = robust_read_csv(out / "comments_dedup.csv", dtype=str)
    texts = df["text_clean"].astype(str).tolist()
    max_samples = bcfg.get("max_samples", 0)
    if max_samples and len(texts) > max_samples:
        idx = np.random.RandomState(cfg["runtime"].get("random_seed", 42)).choice(
            len(texts), max_samples, replace=False)
        idx = np.sort(idx)
        texts = [texts[i] for i in idx]
        df_sub = df.iloc[idx].reset_index(drop=True)
    else:
        df_sub = df.reset_index(drop=True)

    model_name = bcfg.get("model", "hfl/chinese-bert-wwm-ext")
    max_len = bcfg.get("max_len", 64)
    log.info("加载模型 %s ...", model_name)
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name)
    model.eval()
    if bcfg.get("quantize", True):
        try:
            model = torch.quantization.quantize_dynamic(model, {torch.nn.Linear}, dtype=torch.qint8)
            log.info("已应用 INT8 动态量化")
        except Exception as e:  # noqa: BLE001
            log.warning("量化失败，使用原始模型：%s", e)

    batch = bcfg.get("batch_size", 64)
    emb_list = []
    for i in range(0, len(texts), batch):
        chunk = texts[i:i + batch]
        enc = tokenizer(chunk, padding=True, truncation=True, max_length=max_len, return_tensors="pytorch")
        with torch.no_grad():
            out_t = model(**enc)
        mask = enc["attention_mask"].unsqueeze(-1).float()
        pooled = (out_t.last_hidden_state * mask).sum(1) / mask.sum(1)
        emb_list.append(pooled.cpu().numpy())

    embeddings = np.vstack(emb_list)
    np.save(out / "bert_comment_embeddings.npy", embeddings)
    df_sub[["comment_id", "text_clean"]].to_csv(out / "bert_embed_map.csv", index=False, encoding="utf-8-sig")
    log.info("句向量: %s -> bert_comment_embeddings.npy", embeddings.shape)

    return {
        "stats": {"n_embed": int(embeddings.shape[0]),
                  "dim": int(embeddings.shape[1]),
                  "model": model_name},
        "figures": [],
        "data_files": ["bert_comment_embeddings.npy", "bert_embed_map.csv"],
    }
