"""Fetch and verify pinned official FinanceBench files; no model calls."""
from run_external_human_audit import dataset
if __name__=='__main__':
    rows=dataset();print(f'Verified {len(rows)} questions and pinned historical responses; raw data stays in data/cache/financebench.')
