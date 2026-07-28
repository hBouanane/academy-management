import { useEffect, useMemo, useState } from "react"
import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

type Student = {
  id: number
  name: string
  group: string
  monthly_fee: number
  paid: boolean
}

type StudentsResponse = {
  students: Student[]
  total: number
  paid: number
  unpaid: number
}

function App() {
  const [data, setData] = useState<StudentsResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState("")

  useEffect(() => {
    fetch("/api/students")
      .then((res) => {
        if (!res.ok) throw new Error(`API responded with ${res.status}`)
        return res.json() as Promise<StudentsResponse>
      })
      .then(setData)
      .catch((err: Error) => setError(err.message))
  }, [])

  const filtered = useMemo(() => {
    if (!data) return []
    const q = search.trim().toLowerCase()
    if (!q) return data.students
    return data.students.filter(
      (s) =>
        s.name.toLowerCase().includes(q) || s.group.toLowerCase().includes(q),
    )
  }, [data, search])

  if (error) {
    return (
      <main className="flex min-h-svh items-center justify-center p-6">
        <Card className="max-w-md">
          <CardHeader>
            <CardTitle>API unreachable</CardTitle>
            <CardDescription>{error}</CardDescription>
          </CardHeader>
        </Card>
      </main>
    )
  }

  return (
    <main className="mx-auto min-h-svh max-w-4xl space-y-6 p-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground text-sm">
          Stack validation spike — data served by FastAPI
        </p>
      </header>

      <section className="grid gap-4 sm:grid-cols-3">
        <Card>
          <CardHeader>
            <CardDescription>Students</CardDescription>
            <CardTitle className="text-3xl">{data?.total ?? "—"}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>Paid this month</CardDescription>
            <CardTitle className="text-3xl">{data?.paid ?? "—"}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>Still owing</CardDescription>
            <CardTitle className="text-3xl">{data?.unpaid ?? "—"}</CardTitle>
          </CardHeader>
        </Card>
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Students</CardTitle>
          <CardDescription>Payment status for the current month</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Input
            placeholder="Search by name or group…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="max-w-sm"
          />
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Group</TableHead>
                <TableHead className="text-right">Monthly fee</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((s) => (
                <TableRow key={s.id}>
                  <TableCell className="font-medium">{s.name}</TableCell>
                  <TableCell>{s.group}</TableCell>
                  <TableCell className="text-right">
                    {s.monthly_fee} MAD
                  </TableCell>
                  <TableCell>
                    {s.paid ? (
                      <Badge>Paid</Badge>
                    ) : (
                      <Badge variant="destructive">Unpaid</Badge>
                    )}
                  </TableCell>
                </TableRow>
              ))}
              {data && filtered.length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={4}
                    className="text-muted-foreground text-center"
                  >
                    No students match “{search}”
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </main>
  )
}

export default App
