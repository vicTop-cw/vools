const vscode = require('vscode');

/**
 * Activate the Vox extension.
 * @param {vscode.ExtensionContext} context
 */
function activate(context) {
    // --- vox.run: Execute voxc run on the current file ---
    const runCmd = vscode.commands.registerCommand('vox.run', () => {
        runVoxCommand('run');
    });

    // --- vox.compile: Execute voxc compile on the current file ---
    const compileCmd = vscode.commands.registerCommand('vox.compile', () => {
        runVoxCommand('compile');
    });

    // --- vox.showAst: Execute voxc ast and show output ---
    const astCmd = vscode.commands.registerCommand('vox.showAst', () => {
        runVoxCommand('ast');
    });

    context.subscriptions.push(runCmd, compileCmd, astCmd);
}

/**
 * Run a voxc subcommand in the integrated terminal or show output.
 * @param {string} subcommand - 'run' | 'compile' | 'ast'
 */
function runVoxCommand(subcommand) {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
        vscode.window.showWarningMessage('No active editor.');
        return;
    }

    const filePath = editor.document.fileName;
    if (!filePath.endsWith('.vox')) {
        vscode.window.showWarningMessage('This command only works with .vox files.');
        return;
    }

    const escapedPath = filePath.replace(/\\/g, '\\\\');

    if (subcommand === 'ast') {
        // Show AST output in the output channel
        const cp = require('child_process');
        const outputChannel = vscode.window.createOutputChannel('Vox AST');
        outputChannel.show(true);
        outputChannel.appendLine(`[voxc ast] ${filePath}`);
        outputChannel.appendLine('');

        try {
            cp.exec(`voxc ast "${escapedPath}"`, (error, stdout, stderr) => {
                if (error) {
                    outputChannel.appendLine(`Error: ${error.message}`);
                    if (stderr) {
                        outputChannel.appendLine(stderr);
                    }
                    return;
                }
                outputChannel.appendLine(stdout || '(empty output)');
                if (stderr) {
                    outputChannel.appendLine('--- stderr ---');
                    outputChannel.appendLine(stderr);
                }
            });
        } catch (err) {
            outputChannel.appendLine(`Failed to execute: ${err.message}`);
        }
    } else {
        // run / compile: use integrated terminal
        const terminal = vscode.window.createTerminal('Vox');
        terminal.show(true);
        terminal.sendText(`voxc ${subcommand} "${escapedPath}"`);
    }
}

function deactivate() {}

module.exports = { activate, deactivate };