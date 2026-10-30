import {defineConfig} from 'vite';
export default defineConfig({server:{proxy:{'/api':'http://127.0.0.1:3042'}},build:{sourcemap:false,rollupOptions:{output:{manualChunks:{react:['react','react-dom','react-dom/client','scheduler']}}}}});
