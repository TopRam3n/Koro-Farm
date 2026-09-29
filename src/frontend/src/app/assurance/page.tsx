import { AuthGate } from '@/components/AuthGate';
import { ControlCenterView } from '@/components/ControlCenterView';

export default function Page() {
	return <AuthGate><ControlCenterView /></AuthGate>;
}
