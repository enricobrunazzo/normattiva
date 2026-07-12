import { serve } from 'https://deno.land/std@0.168.0/http/server.ts'

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
}

serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders })
  }

  try {
    const { input } = await req.json()
    if (!input || typeof input !== 'string') {
      return new Response(
        JSON.stringify({ error: 'Campo "input" mancante o non stringa' }),
        { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    // @ts-ignore: Supabase runtime globals
    const session = new Supabase.ai.Session('gte-small')
    const embedding = await session.run(input.slice(0, 2048), {
      mean_pool: true,
      normalize: true,
    })

    return new Response(
      JSON.stringify({ embedding: Array.from(embedding) }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )
  } catch (err) {
    console.error('[EMBED ERROR]', err)
    return new Response(
      JSON.stringify({ error: String(err) }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )
  }
})
