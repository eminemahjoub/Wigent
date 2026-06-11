#!/usr/bin/env bash
# ============================================
# Wigent - Global Installer (Works Like Kilo)
# ============================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Configuration
WIGENT_REPO="https://github.com/eminemahjoub/Wigent.git"
WIGENT_INSTALL_DIR="$HOME/.wigent"

# Banner
print_banner() {
    echo -e "${CYAN}${BOLD}"
    cat << "EOF"
╔════════════════════════════════════════════════╗
║                                                ║
║   ██╗    ██╗██╗ ██████╗ ███████╗███╗  ██ ████  ║
║   ██║    ██║██║██╔════╝ ██╔════╝████╗ ██  ██   ║
║   ██║ █╗ ██║██║██║  ███╗█████╗  ██╔██╗██║ ██   ║
║   ╚███╔███╔╝██║╚██████╔╝███████╗██║ ╚███╗ ██   ║
║    ╚══╝╚══╝ ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝       ║
║                                                ║
║       🤖 AI Coding Agent                       ║
║                                                ║
║                                                ║
╚════════════════════════════════════════════════╝
EOF
    echo -e "${NC}"
}

log_info() { echo -e "${BLUE}ℹ${NC} $1"; }
log_success() { echo -e "${GREEN}✓${NC} $1"; }
log_warning() { echo -e "${YELLOW}⚠${NC} $1"; }
log_error() { echo -e "${RED}✗${NC} $1"; }

# Check Python 3.11+
check_python() {
    log_info "Checking Python..."
    
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 not installed!"
        echo "Install: sudo apt install python3 python3-pip"
        exit 1
    fi
    
    if ! python3 -c "import sys; exit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null; then
        log_error "Python 3.11+ required"
        exit 1
    fi
    
    log_success "Python OK"
}

# Check Git
check_git() {
    log_info "Checking Git..."
    if ! command -v git &> /dev/null; then
        log_error "Git not installed!"
        echo "Install: sudo apt install git"
        exit 1
    fi
    log_success "Git OK"
}

# Install pipx if needed
install_pipx() {
    log_info "Checking pipx..."
    
    if command -v pipx &> /dev/null; then
        log_success "pipx already installed"
        return 0
    fi
    
    log_warning "Installing pipx..."
    
    # Try apt first (Linux)
    if command -v apt &> /dev/null; then
        sudo apt update -qq
        sudo apt install pipx -y 2>/dev/null || python3 -m pip install --user pipx
    # Try brew (macOS)
    elif command -v brew &> /dev/null; then
        brew install pipx
    # Fallback to pip
    else
        python3 -m pip install --user pipx
    fi
    
    # Ensure PATH
    python3 -m pipx ensurepath 2>/dev/null || pipx ensurepath
    export PATH="$HOME/.local/bin:$PATH"
    
    log_success "pipx installed"
}

# Clone or update repo
setup_repo() {
    log_info "Setting up Wigent repository..."
    
    if [ -d "$WIGENT_INSTALL_DIR" ]; then
        if [ -d "$WIGENT_INSTALL_DIR/.git" ]; then
            log_warning "Existing installation found, pulling updates..."
            cd "$WIGENT_INSTALL_DIR"
            git pull --quiet 2>/dev/null || true
        else
            log_warning "Stale directory found (not a git repo), replacing..."
            # Preserve history and .env across re-install
            [ -f "$WIGENT_INSTALL_DIR/history" ] && cp "$WIGENT_INSTALL_DIR/history" /tmp/.wigent_history_backup 2>/dev/null || true
            [ -f "$WIGENT_INSTALL_DIR/.env" ] && cp "$WIGENT_INSTALL_DIR/.env" /tmp/.wigent_env_backup 2>/dev/null || true
            rm -rf "$WIGENT_INSTALL_DIR"
            git clone --depth 1 "$WIGENT_REPO" "$WIGENT_INSTALL_DIR" --quiet
            [ -f /tmp/.wigent_history_backup ] && mv /tmp/.wigent_history_backup "$WIGENT_INSTALL_DIR/history" || true
            [ -f /tmp/.wigent_env_backup ] && mv /tmp/.wigent_env_backup "$WIGENT_INSTALL_DIR/.env" || true
        fi
    else
        git clone --depth 1 "$WIGENT_REPO" "$WIGENT_INSTALL_DIR" --quiet
    fi
    
    cd "$WIGENT_INSTALL_DIR"
    log_success "Repository ready"
}

# Install wigent globally with pipx
install_wigent() {
    log_info "Installing Wigent globally..."
    log_info "This makes it work like 'kilo' or 'npm' commands"
    
    cd "$WIGENT_INSTALL_DIR"
    
    # Remove old install if exists
    pipx uninstall wigent 2>/dev/null || true
    
    # Install with pipx (THE MAGIC!)
    pipx install -e . --force 2>&1 | tail -5
    
    log_success "Wigent installed globally!"
}

# Verify installation
verify_install() {
    log_info "Verifying installation..."
    
    # Ensure PATH is updated
    export PATH="$HOME/.local/bin:$PATH"
    
    # Reload bashrc
    source ~/.bashrc 2>/dev/null || true
    
    if command -v wigent &> /dev/null; then
        log_success "wigent command available!"
        log_success "Location: $(which wigent)"
    else
        log_warning "wigent not in PATH yet"
        log_info "Run: source ~/.bashrc"
    fi
}

# Run interactive setup wizard
run_setup() {
    echo ""
    log_info "Launching provider setup wizard..."
    
    export PATH="$HOME/.local/bin:$PATH"
    
    if command -v wigent &> /dev/null; then
        wigent setup || log_warning "Setup wizard exited early"
    else
        log_warning "wigent not in PATH yet, skipping setup wizard"
        log_info "Run 'wigent setup' manually after reloading your shell"
    fi
}

# Print completion message
print_completion() {
    echo ""
    echo -e "${GREEN}${BOLD}"
    cat << "EOF"
╔══════════════════════════════════════════╗
║                                          ║
║   ✅ Installation Complete!              ║
║                                          ║
║   Wigent now works EVERYWHERE!          ║
║   Just like kilo, npm, git, etc.        ║
║                                          ║
╚══════════════════════════════════════════╝
EOF
    echo -e "${NC}"
    
    echo ""
    echo -e "${BOLD}🚀 Next Steps:${NC}"
    echo ""
    echo -e "  1. Reload your shell:"
    echo -e "     ${CYAN}source ~/.bashrc${NC}"
    echo ""
    echo -e "  2. Go to any project folder:"
    echo -e "     ${CYAN}cd ~/your-project${NC}"
    echo ""
    echo -e "  3. Run wigent:"
    echo -e "     ${CYAN}wigent${NC}"
    echo ""
    echo -e "${BOLD}🎯 Just like Kilo - works everywhere!${NC}"
    echo ""
}

# Main
main() {
    print_banner
    echo ""
    log_info "Installing Wigent globally..."
    echo ""
    
    check_python
    check_git
    install_pipx
    setup_repo
    install_wigent
    verify_install
    run_setup
    print_completion
}

main "$@"
