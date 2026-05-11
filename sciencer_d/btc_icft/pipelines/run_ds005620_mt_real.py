from __future__ import annotations
import argparse, sys
from sciencer_d.btc_icft.evaluation.ds005620_residual import (
    build_mock_ds005620_level_t_rows, build_mock_ds005620_level_m_rows, join_level_m_t_real_rows,
    evaluate_mt_residual, write_mt_real_outputs, load_level_m_real_features, load_level_t_real_features
)

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument('--m-features',default='outputs/btc_icft/ds005620/m_real/features_m.csv')
    p.add_argument('--t-features',default='outputs/btc_icft/ds005620/t_real/features_t.csv')
    p.add_argument('--out',default='outputs/btc_icft/ds005620/mt_real')
    p.add_argument('--task',default='awake_vs_sedated')
    p.add_argument('--mock-fixture',action='store_true')
    a=p.parse_args(argv)
    try:
        if a.mock_fixture:
            rows=join_level_m_t_real_rows(build_mock_ds005620_level_m_rows(), build_mock_ds005620_level_t_rows())
        else:
            rows=join_level_m_t_real_rows(load_level_m_real_features(a.m_features), load_level_t_real_features(a.t_features))
        res=evaluate_mt_residual(rows,a.task)
        write_mt_real_outputs(res,a.out,rows)
        return 0
    except (FileNotFoundError,ValueError) as e:
        print(str(e) or 'Run run_ds005620_m_real and run_ds005620_t_real first or use --mock-fixture',file=sys.stderr)
        return 1
if __name__=='__main__': raise SystemExit(main())
