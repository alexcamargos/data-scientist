# Start from the standard devcontainer Python image with the latest stable Python version
FROM mcr.microsoft.com/devcontainers/python:latest

# Set environment variables for non-interactive installations
ENV DEBIAN_FRONTEND=noninteractive

# Install Zsh, Oh My Zsh dependencies, and other utilities
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    zsh \
    git \
    curl \
    vim \
    less \
    locales \
    build-essential && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set up locales to avoid warnings
RUN echo "en_US.UTF-8 UTF-8" > /etc/locale.gen && \
    locale-gen

# --- START FIX FOR OH MY ZSH INSTALLATION ---
# Remove potential pre-existing Oh My Zsh installation for root
# This prevents the "The $ZSH folder already exists" error.
RUN rm -rf /root/.oh-my-zsh

# Install Oh My Zsh
# We're running this as root, and it will install to /root by default, then we'll configure
# the vscode user to use it from their home directory later.
RUN sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" "" --unattended
# --- END FIX FOR OH MY ZSH INSTALLATION ---

# Download the custom Zsh theme directly from GitHub
RUN mkdir -p /home/vscode/.oh-my-zsh/themes && \
    curl -fsSL https://raw.githubusercontent.com/JanDeDobbeleer/oh-my-posh/main/themes/kali.omp.json -o /home/vscode/.oh-my-zsh/themes/kali.omp.json && \
    chown -R vscode:vscode /home/vscode/.oh-my-zsh

# Configure Zsh as the default shell for the vscode user
# and apply Oh My Zsh with the custom theme.
# We'll also add a .zshrc that sources the Oh My Zsh setup.
RUN chsh -s $(which zsh) vscode && \
    echo "export PATH=\"$HOME/.local/bin:$PATH\"" >> /home/vscode/.zshrc && \
    echo "source \$HOME/.oh-my-zsh/oh-my-zsh.sh" >> /home/vscode/.zshrc && \
    echo "ZSH_THEME=\"kali.omp.json\"" >> /home/vscode/.zshrc && \
    chown vscode:vscode /home/vscode/.zshrc

# Ensure pip is up-to-date and install pipx
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir pipx && \
    python -m pipx ensurepath

# Install Python development tools using pipx for isolation
RUN pipx install autopep8 && \
    pipx install black && \
    pipx install flake8 && \
    pipx install pylint && \
    pipx install ruff

# Install JupyterLab using pipx for isolation
RUN pipx install jupyterlab

# Install Python data science and visualization libraries globally
# These will be available for any Python script and also for JupyterLab via pipx inject
RUN pip install --no-cache-dir \
    pandas \
    matplotlib \
    seaborn \
    plotly \
    scikit-learn \
    openpyxl # Useful for Excel data

# Inject data science libraries into the JupyterLab pipx environment
# This makes them available within Jupyter notebooks/lab sessions
RUN pipx inject jupyterlab pandas matplotlib seaborn plotly scikit-learn

# [Optional] Create a workspace directory and set ownership
RUN mkdir -p /workspaces && chown vscode:vscode /workspaces
WORKDIR /workspaces
USER vscode

# The postCreateCommand in devcontainer.json will handle requirements.txt
# and any other commands after the container is up.
