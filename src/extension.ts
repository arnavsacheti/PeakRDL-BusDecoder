import * as vscode from "vscode";

export function activate(context: vscode.ExtensionContext): void {
  const disposable = vscode.commands.registerCommand(
    "peakrdl-busdecoder.hello",
    () => {
      vscode.window.showInformationMessage("PeakRDL BusDecoder is ready.");
    }
  );

  context.subscriptions.push(disposable);
}

export function deactivate(): void {
  // no-op
}
