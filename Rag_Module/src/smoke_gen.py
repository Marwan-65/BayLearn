import warnings, sys, time, traceback
warnings.filterwarnings('ignore')
import logging
logging.disable(logging.INFO)  # silence httpx/qdrant noise

try:
    from helpers.config import get_settings
    from ablation.ab_run import build_controller
    from evaluation.test_set import get_test_cases
    from routes._nlp_handlers import _run_batch

    s = get_settings()
    print('GENERATION_BACKEND =', s.GENERATION_BACKEND, flush=True)
    controller, vdb = build_controller(s)
    cases = get_test_cases(dataset='networks')
    seen, subset = set(), []
    for c in cases:
        if c['level'] not in seen:
            seen.add(c['level']); subset.append(c)
    print(f'Running generation for {len(subset)} questions...', flush=True)
    t = time.time()
    tcs, tds = _run_batch(controller=controller, project_id='rag_mixed', cases=subset,
        enable_multi_query=False, enable_hybrid=False, enable_reranker=False,
        enable_compression=False, enable_hyde=False, limit=5)
    vdb.disconnect()
    dt = time.time() - t
    print(f'Generated {len(tcs)} answers in {dt:.1f}s\n', flush=True)
    real = 0
    for i, tc in enumerate(tcs):
        a = tc['answer']
        bad = ('wasn' in a and 'able to generate' in a) or a.strip() == 'GENERATION_TIMEOUT' or len(a.strip()) < 5
        if not bad:
            real += 1
        print(f'  Q{i+1}: {"REAL" if not bad else "FAIL"} ({len(a)} chars) {a[:70].strip()}', flush=True)
    print(f'\nRESULT: {real}/7 real answers via Gemini generation', flush=True)
except Exception as e:
    print('SMOKE TEST ERROR:', type(e).__name__, e, flush=True)
    traceback.print_exc()
