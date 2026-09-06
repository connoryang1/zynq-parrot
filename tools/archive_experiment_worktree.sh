#!/usr/bin/env bash
# Archive one registered local experiment, verify every archived file, and only
# then remove its worktree. Branches and a checkpoint tag remain in the parent.
set -euo pipefail

mode=${1:-}
target=${2:-}
case "$target" in
  /home/coyang/zp-*|/tmp/zynq-parrot-fpga-*) repo=/home/coyang/zynq-parrot ;;
  /home/coyang/bp-*) repo=/home/coyang/zynq-parrot/import/black-parrot ;;
  *) echo 'Refusing path outside the local experiment families' >&2; exit 2 ;;
esac
[[ "$mode" == --check || "$mode" == --execute || "$mode" == --resume ]] || exit 2
[[ -d "$target" && ! -L "$target" && "$(realpath "$target")" == "$target" ]] || exit 2
git -C "$repo" worktree list --porcelain | grep -Fx "worktree $target" >/dev/null || {
  echo "Refusing unregistered worktree: $target" >&2; exit 2;
}
admin=$(git -C "$target" rev-parse --absolute-git-dir)
case "$admin" in
  /home/coyang/zynq-parrot/.git/worktrees/*|/home/coyang/zynq-parrot/.git/modules/import/black-parrot/worktrees/*) ;;
  *) echo "Unexpected administrative directory: $admin" >&2; exit 2 ;;
esac
[[ -f "$admin/gitdir" && "$(<"$admin/gitdir")" == "$target/.git" ]] || exit 2
if [[ -f "$admin/locked" ]]; then
  echo "Refusing locked worktree: $target" >&2; exit 2
fi
# Do not remove a repository which itself owns additional linked worktrees.
if find "$admin" -mindepth 2 -type d -name worktrees -print -quit | grep -q .; then
  echo "Refusing nested linked-worktree owner: $target" >&2; exit 2
fi
# Check real process working directories, not a grep of this command's argv.
for entry in /proc/[0-9]*/cwd; do
  cwd=$(readlink "$entry" 2>/dev/null || true)
  case "$cwd" in "$target"|"$target"/*)
    echo "Refusing in-use directory: $target ($entry)" >&2; exit 2 ;;
  esac
done
head=$(git -C "$target" rev-parse HEAD)
name=${target##*/}
archive_root=/home/coyang/blackparrot-experiment-archive/20260906
archive="$archive_root/$name.tar.gz"
printf '%s %s %s\n' "$mode" "$target" "$head"
[[ "$mode" != --check ]] || exit 0
mkdir -p "$archive_root"
# Worktrees may share hard-linked object files, so serialize verification/removal.
exec 9>"$archive_root/.cleanup.lock"
flock -x 9
if [[ "$mode" == --execute ]]; then
  [[ ! -e "$archive" && ! -e "$archive.partial" ]] || {
    echo "Archive exists; use --resume after inspection: $archive" >&2; exit 2;
  }
  git -C "$repo" tag "archive/worktrees-20260906/$name" "$head"
  git -C "$target" status --porcelain=v1 --untracked-files=all > "$archive_root/$name.status"
  printf 'source=%s\nadmin=%s\nrepository=%s\nhead=%s\n' \
    "$target" "$admin" "$repo" "$head" > "$archive_root/$name.identity"
  # Include dirty/ignored files and nested Git databases; never follow symlinks.
  tar -C / -I 'gzip -1' -cf "$archive.partial" "${target#/}" "${admin#/}"
else
  grep -Fx "source=$target" "$archive_root/$name.identity" >/dev/null
  grep -Fx "head=$head" "$archive_root/$name.identity" >/dev/null
  [[ "$(git -C "$repo" rev-parse "refs/tags/archive/worktrees-20260906/$name")" == "$head" ]]
fi
candidate="$archive.partial"
[[ -f "$candidate" ]] || candidate="$archive"
[[ -f "$candidate" ]] || exit 2
if fuser -s "$candidate"; then
  echo "Refusing archive still in use: $candidate" >&2; exit 3
fi
# Content comparison plus an independent member inventory rejects incomplete
# archives, including tar runs stopped by changed hard-link metadata.
tar -C / -dzf "$candidate"
cmp <(tar -tzf "$candidate" | sed 's:/$::' | LC_ALL=C sort) \
    <(cd /; find "${target#/}" "${admin#/}" -print | LC_ALL=C sort)
if [[ "$candidate" != "$archive" ]]; then mv "$candidate" "$archive"; fi
sha256sum "$archive" > "$archive.sha256"
# --force permits archived dirty files/submodules; no unarchived data is dropped.
git -C "$repo" worktree remove --force "$target"
[[ ! -e "$target" ]] || exit 1
printf 'REMOVED %s ARCHIVE %s\n' "$target" "$archive"
