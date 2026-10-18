"""Explicit ordered local migration runner. Remote targets are blocked before I/O."""
import argparse
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from pydantic import SecretStr
from apps.api.migration_runner import MigrationPlan, MigrationRunner, MigrationBlocked


class SafeParser(argparse.ArgumentParser):
    def error(self, _):
        print(json.dumps({'status':'BLOCKED','stage':'configuration','code':'invalid_arguments'}))
        raise SystemExit(1)


def main(argv=None):
    p=SafeParser(description='No remote migrations; uses SB_PG_TEST_DSN only')
    p.add_argument('--application-schema',required=True)
    p.add_argument('--budget-schema',required=True)
    p.add_argument('--mode',choices=('apply','verify'),default='verify')
    args=p.parse_args(argv)
    error=None
    try:
        plan=MigrationPlan(database_url=SecretStr(os.environ.get('SB_PG_TEST_DSN','')),
                           application_schema=args.application_schema,budget_schema=args.budget_schema)
        result=MigrationRunner(plan).run(mode=args.mode)
    except MigrationBlocked as e:
        error={'status':'BLOCKED','stage':e.stage,'code':e.code}
    except Exception:
        error={'status':'BLOCKED','stage':'configuration','code':'invalid_plan'}
    print(json.dumps(error or result))
    return 1 if error else 0


if __name__=='__main__':raise SystemExit(main())
