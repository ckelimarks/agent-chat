/**
 * Inject context progress bar into agent-chat xterm terminals
 *
 * This script monitors Claude Code sessions in agent-chat and displays
 * a live context progress bar in the xterm.js terminal statusline.
 */

const fs = require('fs');
const path = require('path');

// Terminal ANSI color codes
const colors = {
    green: '\x1b[0;32m',
    yellow: '\x1b[1;33m',
    red: '\x1b[0;31m',
    reset: '\x1b[0m',
    bold: '\x1b[1m'
};

/**
 * Format token count (e.g., 90000 -> "90k")
 */
function formatTokens(num) {
    if (num >= 1000) {
        return `${Math.floor(num / 1000)}k`;
    }
    return num.toString();
}

/**
 * Generate progress bar
 */
function generateProgressBar(usedPct, tokensUsed, tokensMax, modelName) {
    const barWidth = 20;
    const filled = Math.floor((usedPct * barWidth) / 100);
    const empty = barWidth - filled;

    const bar = '█'.repeat(filled) + '░'.repeat(empty);

    // Choose color based on threshold
    let color, warning = '';
    if (usedPct >= 80) {
        color = colors.red;
        warning = ' ⚠ ';
    } else if (usedPct >= 65) {
        color = colors.yellow;
    } else {
        color = colors.green;
    }

    const tokensUsedFmt = formatTokens(tokensUsed);
    const tokensMaxFmt = formatTokens(tokensMax);

    return `${color}${bar} ${Math.round(usedPct)}%${colors.reset} │ ${tokensUsedFmt}/${tokensMaxFmt} │ ${modelName}${warning}`;
}

/**
 * Parse Claude Code session data
 * This would be called when agent-chat receives context updates
 */
function updateStatusline(contextData) {
    const {
        used_percentage = 0,
        current_usage = { input_tokens: 0 },
        context_window_size = 200000,
        model_display_name = 'Claude'
    } = contextData;

    const tokensUsed = current_usage?.input_tokens || 0;

    return generateProgressBar(
        used_percentage,
        tokensUsed,
        context_window_size,
        model_display_name
    );
}

// Test output
if (require.main === module) {
    console.log('\nContext Progress Bar Test:\n');

    // Test cases
    const tests = [
        { used_percentage: 20, current_usage: { input_tokens: 40000 }, context_window_size: 200000, model_display_name: 'Sonnet 4.5' },
        { used_percentage: 67, current_usage: { input_tokens: 134000 }, context_window_size: 200000, model_display_name: 'Sonnet 4.5' },
        { used_percentage: 85, current_usage: { input_tokens: 170000 }, context_window_size: 200000, model_display_name: 'Sonnet 4.5' }
    ];

    tests.forEach((test, i) => {
        console.log(`Test ${i + 1}:`);
        console.log(updateStatusline(test));
        console.log();
    });
}

module.exports = { updateStatusline, generateProgressBar };
