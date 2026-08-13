const path = require('path');

// Production-Default. Dev-Build via `npm run dev` (übergibt --mode development).
module.exports = (env, argv) => {
  const isProduction = (argv && argv.mode) === 'production';

  return {
    entry: './static/overlay.js',
    output: {
      filename: 'overlay.bundle.js',
      path: path.resolve(__dirname, 'static', 'dist'),
    },
    module: {
      rules: [
        {
          test: /\.js$/,
          type: 'javascript/auto', // erlaubt gemischten Import-Stil
          exclude: /node_modules/,
          use: {
            loader: 'babel-loader',
          },
        },
      ],
    },
    resolve: {
      fullySpecified: false, // "gifuct-js" auch ohne ".js"-Erweiterung auflösen
    },
    // Source-Maps separat (nicht inline), damit der Produktions-Bundle klein
    // bleibt, aber im Browser debuggbar ist.
    devtool: isProduction ? 'source-map' : 'eval-source-map',
    mode: isProduction ? 'production' : 'development',
  };
};
