import math
from collections import Counter

import jieba


class RelevanceBM25:
    """
    基于 BM25 的相关性计算器（只依赖 tags 和 msg）
    输出范围：0 ~ 1
    """

    def __init__(self, k1=1.5, b=0.75):
        self.k1 = k1
        self.b = b

    def _bm25_score(self, query_words, doc_words, idf):
        tf = Counter(doc_words)
        doc_len = len(doc_words)
        avgdl = (len(query_words) + len(doc_words)) / 2  # small corpus fallback

        score = 0.0
        for w in query_words:
            if w not in tf:
                continue

            tf_wd = tf[w]
            score += idf[w] * (
                (tf_wd * (self.k1 + 1))
                / (tf_wd + self.k1 * (1 - self.b + self.b * doc_len / avgdl))
            )

        return score

    def calc(self, tags: list[str], msg: str):
        """
        计算 tags 与 msg 的相关度（0~1）
        """
        if not tags or not msg:
            return 0.0

        # ---- 分词 ----
        tag_doc = " ".join(tags)
        q_words = list(jieba.cut(tag_doc))
        d_words = list(jieba.cut(msg))

        # ---- IDF ----
        docs = [q_words, d_words]
        vocab = set(q_words + d_words)

        idf = {}
        N = 2  # 固定值：只有 tags 和 msg 两篇文档
        for w in vocab:
            df = sum(1 for doc in docs if w in doc)
            idf[w] = math.log((N - df + 0.5) / (df + 0.5) + 1)

        # ---- 原始 BM25 分数 ----
        raw = self._bm25_score(q_words, d_words, idf)

        # ---- 归一化（线性可控） ----
        max_score = len(q_words) * (1 + self.k1)
        if max_score <= 0:
            return 0.0

        return round(min(raw / max_score, 1.0), 6)
