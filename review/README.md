# Review and approval

The review loop is:

1. Build a render with `review/build.py --add out/sample-reel.mp4`.
2. Open `review/build/index.html` on the phone where the reel will be judged.
3. Watch each video, choose Approve or Deny, and write notes if needed.
4. Press Copy decisions and save the JSON blob.
5. Merge it with `python3 review/collect.py --file decisions.json -o review/approvals.json`.
6. Promote only an approved render with `python3 review/finalize.py out/sample-reel.mp4`.
7. Publish the static review build with `python3 review/publish.py --all --dry-run` first, then without `--dry-run` after the environment is configured.

The approval state lives in a file rather than in the page because static
hosting cannot write. A review tool that silently forgets a decision is worse
than no review tool.
