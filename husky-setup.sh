#!/bin/sh
[ -d '.husky' ] && husky || mkdir .husky && husky

echo 'npx --no-install commitlint --edit $1' > .husky/commit-msg

echo '#!/bin/sh\n. "$(dirname "$0")/_/husky.sh"\n\nnpm run pre-commit' > .husky/pre-commit
