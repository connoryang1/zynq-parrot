#!/usr/bin/env python3
"""Copy/relink only; compile one copied Syms TU. Never runs a target or elaborates RTL."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from common import (HERE, PREFIX, SYMS, MODEL_SHA, PROPOSAL, RESERVE, ARTIFACT_ALLOCATION, bind, verify, save,
                    require, proposal, fresh_home, tree, identities)


def members(path):
    names = subprocess.check_output(['ar', 't', str(path)], text=True).splitlines()
    require(len(names) == len(set(names)), 'duplicate archive members')
    return {n: hashlib.sha256(subprocess.check_output(['ar', 'p', str(path), n])).hexdigest()
            for n in names}


def guarded_commands(p):
    original = p['compile_argv']
    header = PREFIX + '__pch.h'
    require(original[-6:] == ['-include', header + '.slow', '-c', '-o',
                             SYMS + '.o', SYMS + '.cpp'], 'unexpected compile argv')
    require(p['original_PCH_creation_argv'][:-5] == original[:-6],
            'PCH compiler prefix mismatch')
    require(p['original_PCH_creation_argv'][-5:] ==
            ['-x', 'c++-header', header, '-o', header + '.slow.gch'], 'wrong PCH source')
    mapped = original.copy()
    mapped[-5] = header
    require(mapped == p['textual_header_compile_argv'], 'textual header mapping changed')
    require('-DVM_TRACE=1' in mapped and '-DVM_TRACE_FST=1' in mapped,
            'TRACE=1 FST flags absent')
    link = p['link_argv']
    expected = ['ps.o', 'main.o', 'bsg_nonsynth_dpi_clock_gen.o', 'verilated.o',
                'verilated_dpi.o', 'verilated_fst_c.o', 'verilated_threads.o']
    require([v for v in link if v.endswith(('.o', '.a'))] ==
            expected + [PREFIX + '__ALL.a'], 'frozen object order changed')
    require(link[-2:] == ['-o', PREFIX] and mapped[0] == link[0] == 'g++',
            'unexpected host executable/output')
    for argv in (mapped, link):
        require(not any(v in {'|', '&&', ';', '>', '2>&1'} for v in argv), 'shell argv')
    return mapped, link


def filtered_source(text, leaves):
    needle = '        __Vm_modelp->trace(__Vm_dumperp, 0, 0);\n'
    require(text.count(needle) == 1 and text.index(needle) < text.index('__Vm_dumperp->open('),
            'ambiguous trace registration/open')
    require(len(leaves) == len({r['path'] for r in leaves}), 'duplicate filter leaves')
    addition = ('        // Host observation only; target evaluation remains frozen.\n' +
                ''.join('        __Vm_dumperp->dumpvars(1, ' + json.dumps(r['path']) + ');\n'
                        for r in leaves))
    return text.replace(needle, needle + addition), addition


def changed_files(before, after):
    require(set(before) == set(after), 'unexpected file creation/deletion')
    changes = [n for n in before if identities(before)[n] != identities(after)[n]]
    allowed = {SYMS + '.cpp', SYMS + '.o', SYMS + '.d', PREFIX + '__ALL.a', PREFIX}
    require(set(changes) <= allowed and {SYMS + '.cpp', SYMS + '.o'} <= set(changes),
            'non-observation generated file changed')
    return changes


def run(argv, cwd, evidence, name):
    save(evidence / (name + '.argv.json'), argv)
    with (evidence / (name + '.log')).open('w') as f:
        subprocess.run(argv, cwd=cwd, stdout=f, stderr=subprocess.STDOUT,
                       check=True, timeout=600)


def build(output):
    output = fresh_home(output)
    p = proposal()
    compiler, linker = guarded_commands(p)
    original = Path(p['original_generated_root'])
    for item in [p['model'], p['original_build_log'], p['PCH_textual_header'],
                 *p['reviewed_runtime'].values()]:
        verify(item)
    for item in p['compiled_sources'].values():verify(item)
    before = tree(original)
    require(identities(before) == identities(p['original_generated_files']),
            'original generated inventory changed')
    require(shutil.disk_usage(output.parent).free > RESERVE + ARTIFACT_ALLOCATION +
            p['estimated_copy_bytes_without_PCH'] + 256 * 1024 * 1024,
            'insufficient build space after3GiB reserve+fixed artifact allocation')
    output.mkdir()
    evidence = output / 'evidence'; evidence.mkdir()
    manifest = evidence / 'build.json'
    state = dict(state='BUILDING-no-target-execution', proposal=bind(PROPOSAL),
                 builder=bind(__file__), helper=bind(HERE / 'common.py'),
                 original_files=before, original_model=p['model'], source_freeze=p['source_freeze'],
                 reserve_bytes=RESERVE,fixed_artifact_allocation_bytes=ARTIFACT_ALLOCATION,
                 commands=dict(compile=compiler,link=linker))
    save(manifest, state)
    try:
        obj = output / 'obj'
        shutil.copytree(original, obj, ignore=shutil.ignore_patterns('*.gch'))
        require(identities(tree(obj)) == identities(before), 'copy differs')
        archive = obj / (PREFIX + '__ALL.a')
        initial_members = members(archive)
        require(initial_members == p['archive_member_sha256'], 'original archive members changed')
        run(linker, obj, evidence, 'baseline-link')
        require(bind(obj / PREFIX)['sha256'] == MODEL_SHA,
                'untouched relink did not reproduce f65c; stop before filter')
        state['baseline_relink'] = bind(obj / PREFIX)
        save(manifest, state)
        source = obj / (SYMS + '.cpp')
        modified, addition = filtered_source(source.read_text(), p['filter_leaves'])
        source.write_text(modified)
        (evidence / 'inserted-filter.txt').write_text(addition)
        run(compiler, obj, evidence, 'compile-syms')
        run(['ar', 'rcs', archive.name, SYMS + '.o'], obj, evidence, 'replace-syms')
        final_members = members(archive)
        require(list(initial_members) == list(final_members), 'archive member order changed')
        require([n for n in initial_members if initial_members[n] != final_members[n]] ==
                [SYMS + '.o'], 'archive changed beyond Syms.o')
        run(linker, obj, evidence, 'filtered-link')
        after = tree(obj)
        changes = changed_files(before, after)
        require(identities(tree(original)) == identities(before), 'original tree mutated')
        for item in p['compiled_sources'].values():verify(item)
        freeze=json.loads(Path(p['source_freeze']['path']).read_text())
        env=dict(os.environ);env.update(freeze['environment'])
        linked=subprocess.run(['ldd',str(obj/PREFIX)],env=env,capture_output=True,text=True,timeout=10)
        require(linked.returncode==0 and 'not found' not in linked.stdout,'filtered loader preflight failed')
        (evidence/'filtered-loader.log').write_text(linked.stdout);libraries=[]
        for line in linked.stdout.splitlines():
            for word in line.split():
                if word.startswith('/') and Path(word).is_file():libraries.append(bind(word))
        require(libraries==freeze['linked_libraries'],'original/filtered loader libraries differ')
        verify(freeze['model_stamp'])
        require(shutil.disk_usage(output.parent).free > RESERVE+ARTIFACT_ALLOCATION,
                'remaining3GiB reserve+fixed artifact allocation violated')
        state.update(state='BUILT-NOT-TARGET-QUALIFIED', binary=bind(obj / PREFIX),
                     final_files=after, changed_files=changes,
                     original_archive_members=initial_members, final_archive_members=final_members,
                     compiler_binary=bind(shutil.which('g++')),linked_libraries=libraries,
                     original_stamp=freeze['model_stamp'],environment=freeze['environment'])
    except BaseException as e:
        state.update(state='FAIL-build-preserved-no-target-admission', error=repr(e))
        raise
    finally:
        state['original_inventory_unchanged'] = identities(tree(original)) == identities(before)
        save(manifest, state)
    print(manifest, state['state'], flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    build(ap.parse_args().output)
