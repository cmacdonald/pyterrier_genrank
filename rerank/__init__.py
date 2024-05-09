from rerank.data import Candidate, Request, Query
from rerank.rank_listwise_os_llm import RankListwiseOSLLM

from rerank.reranker import Reranker
import pandas as pd
import pyterrier as pt

class LLMReRanker(pt.Transformer):
    def __init__(self, model_path="castorini/rank_vicuna_7b_v1", num_few_shot_examples=0, top_k_candidates=100,
                 window_size=20,
                 shuffle_candidates=False,
                 print_prompts_responses=False, step_size=10, variable_passages=True,
                 system_message='You are RankLLM, an intelligent assistant that can rank passages based on their relevancy to the query.',
                 num_gpus=1,
                 text_key='text'):
        self.window_size = window_size
        self.shuffle_candidates = shuffle_candidates
        self.top_k_candidates = top_k_candidates
        self.print_prompts_responses = print_prompts_responses
        self.step_size = step_size
        self.agent = RankListwiseOSLLM(model=model_path,
                                       num_few_shot_examples=num_few_shot_examples,
                                       num_gpus=num_gpus,
                                       variable_passages=variable_passages,
                                       system_message=system_message,
                                       )
        self.reranker = Reranker(self.agent)
        self.text_key = text_key # to allow fields other than 'text' to be used for reranking
    def transform(self, retrieved):
        retrieved = retrieved.copy()
        query = Query(text=retrieved.iloc[0].query, qid=retrieved.iloc[0].qid)
        candidates = []
        for i, row in enumerate(retrieved.itertuples(index=False, name='Candidate')):
            candidate = Candidate(docid=row.docno, score=row.score, doc={'text' : getattr(row, self.text_key)})
            candidates.append(candidate)
        request = Request(query=query, candidates=candidates)
        rerank_results = self.reranker.rerank(
            request,
            rank_end=self.top_k_candidates,
            window_size=min(self.window_size, self.top_k_candidates),
            shuffle_candidates=self.shuffle_candidates,
            logging=self.print_prompts_responses,
            step=self.step_size,
        )
        retrieved.rename(columns={'score': 'score_0'}, inplace=True)
        reranked_df = pd.DataFrame({
            'docno': [c.docid for c in rerank_results.candidates],
            'score': [1/(r+1) for r, c in enumerate(rerank_results.candidates)], # reciprocal ranking
            'rank' : [r for r, c in enumerate(rerank_results.candidates)]
        })
        result_df = retrieved.merge(reranked_df, on='docno', suffixes=('_orig', ''))
        return result_df
