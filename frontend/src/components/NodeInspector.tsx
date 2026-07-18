import type { ArchitectureComponent, ArchitectureData } from "../api";
import { componentStory, kindLabel } from "../lib/flowNarrative";

type Props = {
  component: ArchitectureComponent;
  data: ArchitectureData;
  onClose: () => void;
};

export function NodeInspector({ component, data, onClose }: Props) {
  const story = componentStory(component, data);
  return (
    <div className="inspector">
      <div className="inspector-head">
        <div>
          <p className="inspector-kicker">{kindLabel(component.kind)}</p>
          <h2>{component.name}</h2>
        </div>
        <button type="button" className="inspector-close" onClick={onClose} aria-label="Close">
          ×
        </button>
      </div>
      <p className="inspector-role">{story.role}</p>

      <section>
        <h3>What comes in</h3>
        {story.inbound.length ? (
          <ul>
            {story.inbound.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        ) : (
          <p className="muted">No inbound flow steps mapped to this node yet.</p>
        )}
      </section>

      <section>
        <h3>What goes out</h3>
        {story.outbound.length ? (
          <ul>
            {story.outbound.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        ) : (
          <p className="muted">No outbound flow steps mapped to this node yet.</p>
        )}
      </section>

      <section>
        <h3>Files in this component</h3>
        <ul className="file-chips">
          {story.files.map((f) => (
            <li key={f}>{f}</li>
          ))}
        </ul>
      </section>
    </div>
  );
}
