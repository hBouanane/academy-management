import { MessageTemplates } from "@/components/MessageTemplates"
import { Notice } from "@/components/Notice"
import { useAlert } from "@/lib/alert"

/**
 * Les messages qu'on envoie aux familles.
 *
 * Ils étaient rangés au fond de la page Académie, entre le partage des
 * pourcentages et les sauvegardes — trois choses qui n'ont rien à voir.
 * Ce qu'on écrit aux familles mérite son écran : on y vient pour ça, et
 * on le retrouve sans chercher.
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
