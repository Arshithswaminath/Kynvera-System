# Shared git branch helpers for Injaaz dev shell.
# Source from env.sh, run, work, or install-dev-shell.sh.

injaaz_git_branch() {
  git -C "${1:-$PWD}" branch --show-current 2>/dev/null
}

injaaz_set_terminal_branch() {
  local root="${1:-$PWD}"
  local branch
  branch="$(injaaz_git_branch "$root")"
  if [[ -n "$branch" ]]; then
    export INJAAZ_BRANCH="$branch"
    printf '\033]0;Injaaz · %s\007' "$branch"
  else
    unset INJAAZ_BRANCH
  fi
}

injaaz_print_branch_banner() {
  local root="${1:-$PWD}"
  local branch
  branch="$(injaaz_git_branch "$root")"
  if [[ -n "$branch" ]]; then
    printf '\033[36m◆ branch:\033[0m %s\n' "$branch"
  fi
}
