// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "../alert-dialog";

afterEach(() => {
  cleanup();
});

function TestAlertDialog({
  onAction,
  onCancel,
}: {
  onAction: () => void;
  onCancel: () => void;
}) {
  return (
    <AlertDialog>
      <AlertDialogTrigger>Open</AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogTitle>Confirmar acción</AlertDialogTitle>
        <AlertDialogDescription>¿Seguro que quieres continuar?</AlertDialogDescription>
        <div className="flex gap-2 mt-4">
          <AlertDialogCancel onClick={onCancel}>Cancelar</AlertDialogCancel>
          <AlertDialogAction onClick={onAction}>Confirmar</AlertDialogAction>
        </div>
      </AlertDialogContent>
    </AlertDialog>
  );
}

describe("AlertDialog", () => {
  it("fires the action onClick when the confirm button is clicked", async () => {
    const user = userEvent.setup();
    const onAction = vi.fn();
    const onCancel = vi.fn();

    const { container } = render(<TestAlertDialog onAction={onAction} onCancel={onCancel} />);

    // Open dialog — use within container to avoid portal ambiguity
    await user.click(within(container).getByText("Open"));

    // Dialog content renders in portal; search document-wide
    expect(screen.getByText("Confirmar acción")).toBeInTheDocument();

    // Click confirm
    await user.click(screen.getByText("Confirmar"));

    expect(onAction).toHaveBeenCalledTimes(1);
    expect(onCancel).not.toHaveBeenCalled();
  });

  it("fires the cancel onClick when the cancel button is clicked", async () => {
    const user = userEvent.setup();
    const onAction = vi.fn();
    const onCancel = vi.fn();

    const { container } = render(<TestAlertDialog onAction={onAction} onCancel={onCancel} />);

    await user.click(within(container).getByText("Open"));

    expect(screen.getByText("¿Seguro que quieres continuar?")).toBeInTheDocument();

    await user.click(screen.getByText("Cancelar"));

    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onAction).not.toHaveBeenCalled();
  });
});
