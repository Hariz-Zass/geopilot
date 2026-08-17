#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/../frontend"
npm run typecheck
npm run test
npm run lint
npm run build
