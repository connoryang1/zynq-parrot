#!/usr/bin/env python3
"""Exact, enumerated workload-only derivative of the frozen plain benchmark."""
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "linux-tests/scheduler_retained29_benchmark.c"
NEW = ROOT / "linux-tests/scheduler_retained29_regex_benchmark.c"
BASE_SHA = "65adf577913f2c869ee7f97e9f43b706698e714f8634a0df12135569b9d52be9"
REPLACEMENTS = [
    (" * Separate ABI29 matched-lifecycle experiment, not a legacy policy alias.",
     " * Separate real-POSIX-regex ABI29 derivative; see retained29-regex-benchmark provenance."),
    ('#include "resume_workload.h"', '#include "retained29_regex_workload.h"'),
    ("ABI29 natural-workload experiment does not include zlib", "ABI29 regex experiment does not include zlib"),
    ('"RESUME_RETAINED29_HOST_VERIFY_"', '"RESUME_RETAINED29_REGEX_HOST_VERIFY_"'),
    ('"RESUME_RETAINED29_"', '"RESUME_RETAINED29_REGEX_"'),
    ("resume_workload_", "retained29_regex_"),
    ("struct resume_workload", "struct retained29_regex_workload"),
    ('if (retained29_regex_init(&work, kind, kib, salt)) fail("working-set allocation");',
     '(void)kind; /* CLI admits only regex; keep the plain transport signature. */\n\tif (retained29_regex_init(&work, kib, salt)) fail("regex workload allocation/compile");'),
    ('fail("working-set checksum")', 'fail("regex workload checksum")'),
    ('static struct retained29_regex_workload allocate_work(unsigned kib, unsigned salt, const char *kind)',
     'static void allocate_work(struct retained29_regex_workload *work, unsigned kib, unsigned salt, const char *kind)'),
    ('\n\tstruct retained29_regex_workload work;\n\t(void)kind;', '\n\t(void)kind;'),
    ('retained29_regex_init(&work, kib, salt)', 'retained29_regex_init(work, kib, salt)'),
    ('\n\treturn work;\n}\n\nstatic void check_free', '\n}\n\nstatic void check_free'),
    ('struct retained29_regex_workload work = allocate_work(kib, pipe_mode ? 0x5a : 0x3c, kind);',
     'struct retained29_regex_workload work;\n\t\tallocate_work(&work, kib, pipe_mode ? 0x5a : 0x3c, kind);'),
    ('struct retained29_regex_workload work = allocate_work(kib, pipe_mode ? 0xa5 : 0xc3, kind);',
     'struct retained29_regex_workload work;\n\tallocate_work(&work, kib, pipe_mode ? 0xa5 : 0xc3, kind);'),
    ('*kind = "scan"', '*kind = "regex"'),
    ('[scan|lookup|parse|chase]', '[regex]'),
    ('"corpus-kib", 0, 65536', '"corpus-kib", 32, 128'),
    ('(strcmp(kind, "scan") && strcmp(kind, "lookup") && strcmp(kind, "parse") && strcmp(kind, "chase"))',
     '(strcmp(kind, "regex") || (kib != 32 && kib != 128))'),
]


def derived():
    raw = BASE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == BASE_SHA, "frozen plain source changed"
    text = raw.decode()
    applied = []
    for before, after in REPLACEMENTS:
        count = text.count(before)
        assert count, before
        applied.append(dict(before=before, after=after, occurrences=count))
        text = text.replace(before, after)
    return text, applied


def verify():
    expected, replacements = derived()
    assert NEW.read_text() == expected, "derivative includes changes beyond whitelist"
    return dict(base=str(BASE), base_sha256=BASE_SHA, derivative=str(NEW),
                derivative_sha256=hashlib.sha256(NEW.read_bytes()).hexdigest(),
                replacements=replacements,
                invariant="All bytes outside these substitutions equal the frozen plain source; controller, transport, WHOLE/resource/cleanup ordering preserved")


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    print(json.dumps(verify(), indent=2))
    print("".join(difflib.unified_diff(BASE.read_text().splitlines(True), NEW.read_text().splitlines(True),
                                      fromfile=str(BASE), tofile=str(NEW))))
