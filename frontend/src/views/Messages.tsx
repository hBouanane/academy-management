import { MessageTemplates } from "@/components/MessageTemplates"
import { Notice } from "@/components/Notice"
import { useAlert } from "@/lib/alert"

/**
 * The messages sent to families.
 *
 * They were filed at the bottom of the Academy page, between the
 * percentage split and the backups -- three things with nothing to do
 * with one another. What one writes to families deserves its own screen:
 * you come here for that, and you find it again without searching.
 */
export function Messages() {
  const [error, setError] = useAlert()

  return (
    <div className="view-enter max-w-3xl space-y-6">
      <header>
        <h2 className="text-2xl font-medium tracking-tight">Messages</h2>
        <p className="text-muted-foreground text-sm">
          Ce que vous écrivez aux familles sur WhatsApp — écrit une fois,
          proposé sur chaque élève
        </p>
      </header>

      <Notice alert={error} />
      <MessageTemplates onError={setError} />
    </div>
  )
}
