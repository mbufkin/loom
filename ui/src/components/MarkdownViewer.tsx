import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface Props {
  text: string;
  // Called when a link points at another in-repo file we can render/open.
  onNavigate?: (relPath: string) => void;
}

// Renders run markdown with GFM tables. Intercepts links that look like
// repo-relative artifact paths so a reviewer can click straight through the
// dashboard into a unit report without leaving the console.
export function MarkdownViewer({ text, onNavigate }: Props) {
  return (
    <div className="md">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a({ href, children, ...rest }) {
            const target = href ?? "";
            const isExternal = /^https?:\/\//i.test(target);
            const isInternalDoc =
              !isExternal && /\.(md|json)(#.*)?$/i.test(target);
            if (isInternalDoc && onNavigate) {
              return (
                <a
                  href={target}
                  onClick={(e) => {
                    e.preventDefault();
                    onNavigate(target.replace(/^\.\//, ""));
                  }}
                  {...rest}
                >
                  {children}
                </a>
              );
            }
            return (
              <a
                href={target}
                target={isExternal ? "_blank" : undefined}
                rel={isExternal ? "noreferrer" : undefined}
                {...rest}
              >
                {children}
              </a>
            );
          },
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
