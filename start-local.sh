#!/bin/bash
# ============================================
# Auditree Odoo Local Development Starter
# ============================================

ODOO_DIR="/home/fowadhamza/Projects/Auditree/auditreelive-server"
CONF_FILE="/home/fowadhamza/Projects/Auditree/local-dev.conf"
LOG_FILE="/home/fowadhamza/Projects/Auditree/odoo-local.log"
PID_FILE="/home/fowadhamza/Projects/Auditree/odoo-local.pid"
DB_NAME="AUDITREE_LIVE_NEW"
PORT="8069"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

start() {
    echo -e "${YELLOW}Starting Odoo locally...${NC}"

    # Check if already running
    if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
        echo -e "${RED}Odoo is already running (PID: $(cat $PID_FILE))${NC}"
        echo "  → Use './start-local.sh stop' to stop it first"
        exit 1
    fi

    # Check PostgreSQL
    if ! pg_isready -q 2>/dev/null; then
        echo -e "${YELLOW}PostgreSQL not ready, starting...${NC}"
        echo 'PQAutomation@12' | sudo -S service postgresql start
        sleep 2
    fi
    echo -e "${GREEN}✓ PostgreSQL is running${NC}"

    # Check DB exists
    if ! psql -U fowadhamza -d "$DB_NAME" -c '\q' 2>/dev/null; then
        echo -e "${RED}Database '$DB_NAME' not accessible. Check PostgreSQL setup.${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ Database '$DB_NAME' accessible${NC}"

    # Start Odoo in background
    echo -e "${YELLOW}Starting Odoo on http://localhost:${PORT} ...${NC}"
    cd "$ODOO_DIR"
    setsid python3 odoo-bin --config="$CONF_FILE" > "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"

    sleep 3

    if kill -0 $(cat "$PID_FILE") 2>/dev/null; then
        echo -e "${GREEN}✓ Odoo started! PID: $(cat $PID_FILE)${NC}"
        echo -e "${GREEN}  → URL: http://localhost:${PORT}${NC}"
        echo -e "${GREEN}  → Logs: tail -f $LOG_FILE${NC}"
    else
        echo -e "${RED}✗ Odoo failed to start. Check logs:${NC}"
        tail -20 "$LOG_FILE"
        exit 1
    fi
}

stop() {
    echo -e "${YELLOW}Stopping Odoo...${NC}"
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            kill "$PID"
            rm -f "$PID_FILE"
            echo -e "${GREEN}✓ Odoo stopped (PID: $PID)${NC}"
        else
            echo -e "${YELLOW}Odoo was not running (stale PID file removed)${NC}"
            rm -f "$PID_FILE"
        fi
    else
        # Try finding by process name
        PIDS=$(pgrep -f "auditreelive-server/odoo-bin" 2>/dev/null)
        if [ -n "$PIDS" ]; then
            kill $PIDS
            echo -e "${GREEN}✓ Odoo stopped${NC}"
        else
            echo -e "${YELLOW}Odoo is not running${NC}"
        fi
    fi
}

upgrade() {
    MODULE=${2:-hr_holidays}
    echo -e "${YELLOW}Upgrading module: $MODULE on DB: $DB_NAME${NC}"

    # Stop if running
    if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
        echo "Stopping Odoo first..."
        stop
        sleep 2
    fi

    cd "$ODOO_DIR"
    python3 odoo-bin \
        --config="$CONF_FILE" \
        -d "$DB_NAME" \
        -u "$MODULE" \
        --stop-after-init \
        2>&1 | grep -E "INFO|WARNING|ERROR|Upgrade|Loading module|done"

    echo -e "${GREEN}✓ Upgrade complete. Run './start-local.sh start' to restart.${NC}"
}

logs() {
    echo -e "${YELLOW}Following Odoo logs (Ctrl+C to stop)...${NC}"
    tail -f "$LOG_FILE"
}

status() {
    if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
        echo -e "${GREEN}✓ Odoo is RUNNING (PID: $(cat $PID_FILE))${NC}"
        echo -e "  → URL: http://localhost:${PORT}"
    else
        echo -e "${RED}✗ Odoo is NOT running${NC}"
    fi
    echo ""
    echo "Recent log:"
    tail -5 "$LOG_FILE" 2>/dev/null || echo "(no log file yet)"
}

# ---- Main ----
case "$1" in
    start)   start ;;
    stop)    stop ;;
    restart) stop; sleep 2; start ;;
    upgrade) upgrade "$@" ;;
    logs)    logs ;;
    status)  status ;;
    *)
        echo "Usage: $0 {start|stop|restart|upgrade [module]|logs|status}"
        echo ""
        echo "  start            → Start Odoo on http://localhost:${PORT}"
        echo "  stop             → Stop Odoo"
        echo "  restart          → Stop then start"
        echo "  upgrade [module] → Upgrade a module (default: hr_holidays)"
        echo "  logs             → Tail the log file"
        echo "  status           → Show running status"
        ;;
esac
