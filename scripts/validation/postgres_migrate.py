"""Explicit, additive local-test migration. Never accepts a cloud target."""
import argparse
import json
import os
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from apps.api.postgres import PostgresDatabase, PostgresFailure


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--schema', required=True)
    parser.add_argument('--kind', choices=('application','budget'), default='application')
    args = parser.parse_args()
    try:
        database = PostgresDatabase(os.environ.get('SB_PG_TEST_DSN',''), args.schema, local_test=True)
        applied = database.migrate(args.kind)
        print(json.dumps({'status':'APPLIED' if applied else 'ALREADY_APPLIED','migration':1,'kind':args.kind,'target':'LOOPBACK_TEST_ONLY'}))
        return 0
    except (ValueError,PostgresFailure):
        print(json.dumps({'status':'BLOCKED','error':'postgres_local_migration_failed'}))
        return 1


if __name__=='__main__':raise SystemExit(main())
