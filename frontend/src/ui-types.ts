import type { ComponentType, ReactNode } from 'react';
export type UIComponents = {
  Button: ComponentType<{ label: string; variant?: 'ghost'; icon?: ReactNode; isIconOnly?: boolean; onClick?: () => void }>;
  Badge: ComponentType<{ label: string; variant: 'success' | 'neutral' }>;
  Card: ComponentType<{ className?: string; padding: 0; children: ReactNode }>;
  Switch: ComponentType<{ label: string; value: boolean; onChange: (value: boolean) => void; isLabelHidden?: boolean; isDisabled?: boolean }>;
};
