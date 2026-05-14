import { defineConfig } from 'rollup';
import resolve from '@rollup/plugin-node-resolve';
import commonjs from '@rollup/plugin-commonjs';
import terser from '@rollup/plugin-terser';

const isProd = process.env.NODE_ENV === 'production';

export default defineConfig({
  input: 'src/content.js', // Точка входа (наш будущий оркестратор)

  output: {
    file: 'dist/content.bundle.js', // Итоговый собранный файл
    format: 'iife',                 // Безопасный формат для MV3
    name: 'VibeCoder',
    sourcemap: !isProd,
    extend: false,
  },

  plugins: [
    resolve({
      browser: true,
      preferBuiltins: false,
    }),
    commonjs(),
    isProd && terser({
      compress: {
        drop_console: false, // Оставляем console.log для дебага
        drop_debugger: true,
      },
      mangle: {
        reserved: ['chrome'],
      },
      format: {
        comments: false,
      },
    }),
  ].filter(Boolean),

  onwarn(warning, warn) {
    if (warning.code === 'CIRCULAR_DEPENDENCY') {
      throw new Error(`Обнаружена циклическая зависимость: ${warning.message}`);
    }
    warn(warning);
  },
});