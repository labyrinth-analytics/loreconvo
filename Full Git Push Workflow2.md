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

#If there’s a git lock
rm .git/HEAD.lock  # if still there

#Helpful Information
The first screenshot (only finance_analytics visible) was taken while your browser was showing your profile as seen by someone not logged in — private repos are hidden from public view. The second screenshot (showing side_hustle, job_skills, finance_analytics) is the real view when logged in as debbie-shapiro, and side_hustle is right there, updated 1 minute ago.

Your setup is clean:
##GitLab
labyrinth-analytics-consulting-group

###Repositories
* labyrinth-analytics
* labyrinth-analytics-consulting-project
* labyrinth-analytics-website
* secret_agent_man


##GitHub
debbie-shapiro (your personal account) owns:
 
* side_hustle (private)
* job_skills (private) 
* finance_analytics (public)

labyrinth-analytics (your business account) owns (all public):
 
* loreconvo
* loreproject
* claude-plugins 

debbie-shapiro is a collaborator on the labyrinth-analytics repos, so you can push to all of them from one terminal session. 
gh auth setup-git is now configured so git uses the right credentials automatically.

The one thing to watch going forward: if you ever log into gh CLI as labyrinth-analytics again (for any reason), run 

gh auth switch --user debbie-shapiro 

afterward to restore the active account. That's the only way this breaks.