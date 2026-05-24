import { useState, useEffect } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { postFeedback } from '../lib/api'

interface Props { open: boolean; onClose: () => void }

export function FeedbackModal({ open, onClose }: Props) {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [comments, setComments] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!open) { setName(''); setEmail(''); setComments(''); setError(''); setSuccess(false) }
  }, [open])

  async function submit() {
    if (!comments.trim()) { setError('Comments are required.'); return }
    setError('')
    setSubmitting(true)
    try {
      await postFeedback({ name, email, comments })
      setSuccess(true)
      setTimeout(() => { setSuccess(false); onClose() }, 1500)
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { comments?: string; message?: string } | string } }
      const data = axiosErr?.response?.data
      const msg = (typeof data === 'object' && data !== null)
        ? (data.comments || data.message)
        : (typeof data === 'string' ? data : null)
      setError(msg || 'Failed to submit feedback. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="bg-slate-900 border-slate-700">
        <DialogHeader><DialogTitle className="text-white">Send Feedback</DialogTitle></DialogHeader>
        {success ? (
          <p className="text-green-400 text-sm py-4 text-center">Thanks for your feedback!</p>
        ) : (
          <div className="flex flex-col gap-3 pt-2">
            <Input value={name} onChange={e => setName(e.target.value)} placeholder="Name (optional)" className="bg-slate-800 border-slate-700" />
            <Input value={email} onChange={e => setEmail(e.target.value)} placeholder="Email (optional)" className="bg-slate-800 border-slate-700" />
            <textarea
              value={comments}
              onChange={e => setComments(e.target.value)}
              placeholder="Comments *"
              rows={4}
              className="w-full rounded-md bg-slate-800 border border-slate-700 text-white text-sm px-3 py-2 resize-none focus:outline-none focus:ring-1 focus:ring-amber-500"
            />
            {error && <p className="text-red-400 text-xs">{error}</p>}
            <Button onClick={submit} disabled={submitting} className="bg-amber-500 text-black hover:bg-amber-400">
              {submitting ? 'Sending…' : 'Send Feedback'}
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
