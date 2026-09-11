import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

import { isSentryModule } from './build/chunking'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            {
              name: 'sentry-vendor',
              test: isSentryModule,
              priority: 20,
            },
          ],
        },
      },
    },
  },
})
