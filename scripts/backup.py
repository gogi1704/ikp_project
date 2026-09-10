"""Consistent online SQLite backup. Run with the same DATABASE_PATH as the server."""
import argparse
import sqlite3
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from backend.app import DB
parser=argparse.ArgumentParser()
parser.add_argument('destination')
args=parser.parse_args()
if Path(args.destination).exists():
    parser.error('Destination already exists')
with sqlite3.connect(DB) as source, sqlite3.connect(args.destination) as target:
    source.backup(target)
    if target.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
        raise RuntimeError('Backup integrity check failed')
print('Backup complete')
