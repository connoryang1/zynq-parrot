"""Lossless selected-transition canonicalization: names replace handles, tick order retained."""
import collections
import gzip
import hashlib
import shutil
import subprocess
import threading
from pathlib import Path
from common import require, bind, RESERVE

MAX_CANONICAL_BYTES=50*1024*1024


def canonicalize(lines, leaves, emit):
    expected = {r['path']: (i, r['width']) for i, r in enumerate(leaves)}
    require(len(expected) == len(leaves), 'duplicate expected leaf')
    handles = collections.defaultdict(list)
    declared = set(); initialized = set(); counts = collections.Counter()
    fst = None; ended = False; previous = None; updates = collections.defaultdict(list)
    digest = hashlib.sha256(); event_count = 0

    def write(data):
        digest.update(data); emit(data)

    def flush():
        nonlocal event_count
        for index in sorted(updates):
            for value in updates[index]:
                write(('%d\t%d\t%s\n' % (previous, index, value)).encode())
                event_count += 1; counts[index] += 1; initialized.add(index)
        updates.clear()

    for line in lines:
        require(not ended, 'data after clean EOF')
        fields = line.rstrip('\n').split('\t')
        if fields[0] == '#FST':
            require(fst is None and not declared and len(fields) == 4, 'bad FST header')
            fst = tuple(int(v) for v in fields[1:])
            require(fst[0] >= 0 and fst[1] > fst[0], 'empty/reversed FST')
            write(('FST\t%d\t%d\t%d\n' % fst).encode())
            for i, r in enumerate(leaves):
                write(('SIGNAL\t%d\t%d\t%s\n' % (i, r['width'], r['path'])).encode())
        elif fields[0] == '#SIGNAL':
            require(fst is not None and previous is None and len(fields) == 5,
                    'late/bad declaration')
            key, width, handle, path = fields[1:]
            require(path in expected and path not in declared, 'unexpected/duplicate declaration')
            index, wanted = expected[path]
            require(key == 's%03d' % index and int(width) == wanted, 'declaration key/width mismatch')
            handles[int(handle)].append(index); declared.add(path)
        elif fields == ['#END']:
            require(fst is not None and declared == set(expected), 'missing declarations')
            if previous is not None: flush()
            require(initialized == set(range(len(leaves))), 'leaf never initialized')
            write(b'END\n'); ended = True
        else:
            require(len(fields) == 3 and declared == set(expected), 'malformed event/header')
            tick, handle = int(fields[0]), int(fields[1]); value = fields[2]
            require(handle in handles and fst[0] <= tick <= fst[1], 'unknown handle/out-of-range tick')
            require(previous is None or tick >= previous, 'event chronology reversed')
            if previous is not None and tick != previous: flush()
            previous = tick
            for index in handles[handle]:
                width = leaves[index]['width']
                require(len(value) == width and set(value) <= set('01xXzZ'), 'invalid value/width')
                # Keep every transition, including repeated values and same-tick
                # sequences. Only cross-signal serialization order is normalized.
                updates[index].append(value)
    require(ended, 'reader EOF lacks clean #END')
    return dict(sha256=digest.hexdigest(), events=event_count,
                changes_by_index={str(i): counts[i] for i in range(len(leaves))},
                first_tick=fst[0], final_tick=fst[1], timescale=fst[2], clean_EOF=True)


def declarations(text, leaves):
    require(text.rstrip().endswith('#END'), 'hierarchy lacks clean EOF')
    actual = []
    for line in text.splitlines():
        if line.startswith('#VAR\t'):
            _, width, handle, path = line.split('\t')
            actual.append((path, int(width)))
    require(len(actual) == len(set(actual)), 'duplicate hierarchy leaves')
    require(set(actual) == {(r['path'], r['width']) for r in leaves},
            'filtered hierarchy differs from exact reviewed leaves/widths')


def extract(reader, fst, leaves, output, exact_hierarchy):
    output.mkdir()
    if exact_hierarchy:
        listing = subprocess.run([str(reader), str(fst), '--list'], capture_output=True,
                                 text=True, check=True, timeout=60)
        (output / 'hierarchy.tsv').write_text(listing.stdout)
        declarations(listing.stdout, leaves)
    selection = output / 'selection.tsv'
    selection.write_text(''.join('s%03d\t%s\n' % (i, r['path']) for i, r in enumerate(leaves)))
    command = [str(reader), str(fst), str(selection)]
    with (output / 'reader.stderr').open('w') as err, gzip.open(output / 'canonical.tsv.gz', 'wb') as out:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=err, text=True)
        timer = threading.Timer(600, process.kill); timer.daemon = True; timer.start()
        writes=0
        def emit(data):
            nonlocal writes
            out.write(data);writes+=1
            if writes%1024==0:
                require(out.fileobj.tell()<MAX_CANONICAL_BYTES,'fixed50MiB canonical artifact cap exceeded')
                require(shutil.disk_usage(output).free>RESERVE,'3GiB HOME reserve breached during reader audit')
        try:
            result = canonicalize(process.stdout, leaves, emit)
            require(process.wait(timeout=10) == 0, 'reader failed or exceeded600s')
            require(out.fileobj.tell()<MAX_CANONICAL_BYTES,'fixed canonical artifact cap exceeded')
        finally:
            timer.cancel()
            if process.poll() is None: process.kill(); process.wait()
            process.stdout.close()
    result.update(canonical_file=bind(output / 'canonical.tsv.gz'), command=command)
    return result


def equivalent(a, b):
    for key in ('sha256', 'events', 'changes_by_index', 'first_tick', 'final_tick', 'timescale', 'clean_EOF'):
        require(a[key] == b[key], 'complete selected event mismatch: ' + key)
    # Literal decompressed byte comparison as well as digest equality.
    with gzip.open(a['canonical_file']['path'], 'rb') as x, gzip.open(b['canonical_file']['path'], 'rb') as y:
        while True:
            one, two = x.read(1024 * 1024), y.read(1024 * 1024)
            require(one == two, 'canonical byte stream mismatch')
            if not one: break
