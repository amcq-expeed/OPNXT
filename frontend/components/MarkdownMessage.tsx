import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface MarkdownMessageProps {
  children: string;
  className?: string;
}

export default function MarkdownMessage({ children, className }: MarkdownMessageProps) {
  return (
    <div className={`markdown ${className ?? ""}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ node, ...props }) => <p {...props} />,
          ul: ({ node, ...props }) => <ul {...props} />,
          ol: ({ node, ...props }) => <ol {...props} />,
          li: ({ node, ...props }) => <li {...props} />,
          span: ({ node, ...props }) => <span {...props} />,
        }}
        skipHtml={false}
        rehypePlugins={[]}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
