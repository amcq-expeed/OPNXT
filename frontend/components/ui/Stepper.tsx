interface Step {
  id: string;
  label: string;
}

interface StepperProps {
  steps: Step[];
  currentIndex: number; // 0-based
}

export default function Stepper({ steps, currentIndex }: StepperProps) {
  return (
    <div className="stepper" role="group" aria-label="Phase Gate">
      {steps.map((s, i) => (
        <div key={s.id} className={`step ${i < currentIndex ? 'done' : ''} ${i === currentIndex ? 'current' : ''}`} aria-current={i === currentIndex ? 'step' : undefined}>
          <span className="dot" aria-hidden></span>
          <span className="label">{s.label}</span>
          {i < steps.length - 1 && (
            <span className={`connector ${i < currentIndex ? 'done' : ''}`} aria-hidden></span>
          )}
        </div>
      ))}
    </div>
  );
}
