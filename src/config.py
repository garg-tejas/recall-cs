"""Central configuration — loads .env from project root before anything else."""

from __future__ import annotations

from dotenv import find_dotenv, load_dotenv

# find_dotenv() walks up the directory tree looking for .env,
# so it works regardless of which file imports this module.
load_dotenv(find_dotenv(), override=False)
