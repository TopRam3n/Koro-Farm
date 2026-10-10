import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { PaginationControls } from './PaginationControls';

describe('production pagination', () => {
    it('renders the current result range and accessible navigation', () => {
        const view = render(<PaginationControls offset={20} limit={20} total={45} onChange={vi.fn()} />);
        expect(view.getByRole('navigation', { name: 'Results pagination' })).toHaveTextContent('21–40 of 45');
        expect(view.getByRole('button', { name: 'Previous' })).toBeEnabled();
        expect(view.getByRole('button', { name: 'Next' })).toBeEnabled();
    });
});
