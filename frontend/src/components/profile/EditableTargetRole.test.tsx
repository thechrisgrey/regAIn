import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';

import { EditableTargetRole } from './EditableTargetRole';

describe('EditableTargetRole', () => {
  it('renders the current value with an Edit button', () => {
    render(
      <EditableTargetRole value="Senior Cloud Architect" onSave={vi.fn()} />,
    );
    expect(screen.getByText('Senior Cloud Architect')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /edit target role/i })).toBeInTheDocument();
  });

  it('switches to edit mode when Edit is clicked', async () => {
    const user = userEvent.setup();
    render(
      <EditableTargetRole value="Senior Cloud Architect" onSave={vi.fn()} />,
    );
    await user.click(screen.getByRole('button', { name: /edit target role/i }));
    expect(screen.getByLabelText(/target role/i)).toHaveValue('Senior Cloud Architect');
    expect(screen.getByRole('button', { name: /^save$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument();
  });

  it('calls onSave with the trimmed new value', async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<EditableTargetRole value="Old Role" onSave={onSave} />);

    await user.click(screen.getByRole('button', { name: /edit target role/i }));
    const input = screen.getByLabelText(/target role/i);
    await user.clear(input);
    await user.type(input, '  Data Engineer  ');
    await user.click(screen.getByRole('button', { name: /^save$/i }));

    await waitFor(() => expect(onSave).toHaveBeenCalledWith('Data Engineer'));
  });

  it('disables Save when value is empty or unchanged', async () => {
    const user = userEvent.setup();
    render(<EditableTargetRole value="Old" onSave={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: /edit target role/i }));

    const save = screen.getByRole('button', { name: /^save$/i });
    expect(save).toBeDisabled();

    const input = screen.getByLabelText(/target role/i);
    await user.clear(input);
    expect(save).toBeDisabled();

    await user.type(input, 'New');
    expect(save).toBeEnabled();
  });

  it('exits edit mode and discards changes on Cancel', async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    render(<EditableTargetRole value="Old" onSave={onSave} />);

    await user.click(screen.getByRole('button', { name: /edit target role/i }));
    const input = screen.getByLabelText(/target role/i);
    await user.clear(input);
    await user.type(input, 'Should be discarded');
    await user.click(screen.getByRole('button', { name: /cancel/i }));

    expect(screen.getByText('Old')).toBeInTheDocument();
    expect(onSave).not.toHaveBeenCalled();
  });

  it('shows an error message when onSave rejects', async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockRejectedValue(new Error('Server is angry'));
    render(<EditableTargetRole value="Old" onSave={onSave} />);

    await user.click(screen.getByRole('button', { name: /edit target role/i }));
    const input = screen.getByLabelText(/target role/i);
    await user.clear(input);
    await user.type(input, 'New');
    await user.click(screen.getByRole('button', { name: /^save$/i }));

    expect(await screen.findByText(/server is angry/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/target role/i)).toBeInTheDocument();
  });

  it('saves on Enter key and cancels on Escape', async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<EditableTargetRole value="Old" onSave={onSave} />);

    await user.click(screen.getByRole('button', { name: /edit target role/i }));
    const input = screen.getByLabelText(/target role/i);
    await user.clear(input);
    await user.type(input, 'New{Enter}');
    await waitFor(() => expect(onSave).toHaveBeenCalledWith('New'));

    onSave.mockClear();
    await user.click(screen.getByRole('button', { name: /edit target role/i }));
    const input2 = screen.getByLabelText(/target role/i);
    fireEvent.keyDown(input2, { key: 'Escape' });
    expect(screen.getByText('New')).toBeInTheDocument();
    expect(onSave).not.toHaveBeenCalled();
  });
});
