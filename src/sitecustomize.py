"""Python startup hook for the Morning Brief pipeline.

GitHub Actions invokes the pipeline scripts directly as `python src/*.py`.
Python loads sitecustomize from the script directory during startup, so this
provides a reliable pre-AI guard without depending on a workflow-step edit.
The guard is intentionally limited to raw_news.json and is idempotent.
"""

from pathlib import Path

try:
    # Only run inside the Morning Brief repository.
    raw = Path.cwd() / 'data' / 'raw_news.json'
    filter_script = Path.cwd() / 'src' / 'pre_ai_sales_filter.py'
    if raw.exists() and filter_script.exists():
        from pre_ai_sales_filter import main as _run_pre_ai_filter
        _run_pre_ai_filter()
except Exception as exc:
    # Never make Python startup itself fail because the optional sales filter
    # has a problem. The downstream final filter remains as a safety net.
    print(f'[사전 영업활용도 필터] startup hook 건너뜀: {exc}')
