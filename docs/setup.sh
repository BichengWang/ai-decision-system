# git initialization

# if ssh connect fail, then setup ssh key
ssh -T git@github.com 2>&1 | grep -q "Hi abc! You've successfully authenticated, but GitHub does not provide shell access." || ssh-keygen -t ed25519 -C "bichengwang17@gmail.com"

# append content from ./.ssh/config to ~/.ssh/config
cat ./.ssh/config >> ~/.ssh/config

gh ssh-key add ~/.ssh/id_ed25519.pub --title "{key_title}"