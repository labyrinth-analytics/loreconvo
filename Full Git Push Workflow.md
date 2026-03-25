# Full Push Workflow
cd ~/projects/side_hustle

# Private monorepo (all your work)
git push origin master

# Public product repos (when you want to publish updates)
git subtree push --prefix=ron_skills/convovault convovault main

git subtree push --prefix=ron_skills/projectvault projectvault main

#If git push origin master fails:
gh auth switch --user debbie-shapiro  # if labyrinth-analytics is active

gh auth setup-git                      # if no credential helper is configured

#If the remote URL flips to SSH:
git remote set-url origin https://github.com/debbie-shapiro/side_hustle.git