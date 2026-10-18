"""Explicit loopback-only worker test seam; never a production settings bypass."""
import os


def add_postgres_arguments(parser):
    parser.add_argument('--postgres-local-test', action='store_true', help='Use loopback PostgreSQL via SB_PG_TEST_DSN; original files remain under --data-dir')
    parser.add_argument('--postgres-schema', default='sb_application')


def worker_repository(args):
    if args.postgres_local_test:
        from .postgres import PostgresDatabase, PostgresRepository
        return PostgresRepository(PostgresDatabase(os.environ.get('SB_PG_TEST_DSN', ''), args.postgres_schema, local_test=True))
    from .repository import Repository
    return Repository(args.data_dir / 'metadata.sqlite3')
