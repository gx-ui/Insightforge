import {ArtifactsView} from '../../ArtifactViews';
import type {Artifact, SessionSummary} from '../../types';

export default function ArtifactsDrawer({
  session,
  artifacts,
}: {
  session?: SessionSummary;
  artifacts: Artifact[];
}) {
  return (
    <div className="artifacts-drawer-narrow">
      <ArtifactsView session={session} artifacts={artifacts} />
    </div>
  );
}
