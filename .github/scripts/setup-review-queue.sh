#!/usr/bin/env bash
# One-time review-queue setup for a repository (docs/review-queue.md).
# Needs admin rights on the repository and an authenticated gh CLI.
#
#   .github/scripts/setup-review-queue.sh OWNER/REPO CHECK [CHECK...]
#   .github/scripts/setup-review-queue.sh OpenMS/streamlit-template \
#       "test (ubuntu-latest, 3.11)" build lint-manifests assert-invariants
#
# CHECK is a check-run name as shown on a PR. Name only fast checks that pass
# on the default branch today: a red or never-reported required check blocks
# every merge. Re-running replaces the ruleset this script created.
set -euo pipefail

if [ $# -lt 2 ]; then
  sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
  exit 2
fi
REPO=$1; shift
RULESET_NAME="review-queue: default branch"
ACTIONS_APP_ID=15368   # GitHub Actions: only its check runs satisfy a check

# 1. Merge settings: auto-merge on, merge commits for template syncs, squash
#    for everything else, head branches deleted after merge.
gh api -X PATCH "repos/${REPO}" \
  -F allow_auto_merge=true -F allow_merge_commit=true -F allow_squash_merge=true \
  -F delete_branch_on_merge=true >/dev/null
echo "settings: auto-merge, merge commits and squash allowed; merged branches deleted"

# 2. Ruleset on the default branch: changes through PRs, required checks,
#    no force-push or deletion. Repository admins can bypass.
CHECKS=$(printf '%s\n' "$@" | python3 -c '
import json, sys
print(json.dumps([{"context": c.strip(), "integration_id": int(sys.argv[1])}
                  for c in sys.stdin if c.strip()]))' "$ACTIONS_APP_ID")
BODY=$(python3 - "$RULESET_NAME" "$CHECKS" <<'PY'
import json, sys
name, checks = sys.argv[1], json.loads(sys.argv[2])
print(json.dumps({
    "name": name,
    "target": "branch",
    "enforcement": "active",
    "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
    "bypass_actors": [{"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}],
    "rules": [
        {"type": "deletion"},
        {"type": "non_fast_forward"},
        {"type": "pull_request", "parameters": {
            "required_approving_review_count": 0,
            "dismiss_stale_reviews_on_push": False,
            "require_code_owner_review": False,
            "require_last_push_approval": False,
            "required_review_thread_resolution": False}},
        {"type": "required_status_checks", "parameters": {
            "strict_required_status_checks_policy": False,
            "required_status_checks": checks}},
    ],
}))
PY
)
ID=$(gh api "repos/${REPO}/rulesets" --jq ".[] | select(.name == \"${RULESET_NAME}\") | .id" | head -1)
if [ -n "$ID" ]; then
  gh api -X PUT "repos/${REPO}/rulesets/${ID}" --input - <<<"$BODY" >/dev/null
  echo "ruleset ${ID} updated"
else
  gh api -X POST "repos/${REPO}/rulesets" --input - <<<"$BODY" --jq '"ruleset \(.id) created"'
fi
echo "required checks: $*"
