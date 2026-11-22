"""Use exact qualified Make-n implementation with this adapter's source module."""
import importlib.util
from pathlib import Path
P=Path('/home/coyang/fpga-artifacts/context-resume/csr-unmasked256-fullcore-preparation-20261122/preparation02/dryrun.py')
s=importlib.util.spec_from_file_location('qualified1792_dryrun',P);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
layout,verify,perform=m.layout,m.verify,m.perform
