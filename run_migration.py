#!/usr/bin/env python
import os
import sys
from alembic.config import Config
from alembic.command import upgrade

config = Config("alembic.ini")
upgrade(config, "head")
print("✅ Migration completed!")
