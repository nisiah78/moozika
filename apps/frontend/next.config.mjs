/** @type {import('next').NextConfig} */
const nextConfig = {
  // URL du service OMR côté serveur (route proxy). En Docker: http://omr-service:8000
  env: {
    OMR_SERVICE_URL: process.env.OMR_SERVICE_URL ?? "http://localhost:8000",
  },
  // La compression gzip bufferise les petits chunks SSE → Chrome peut
  // suspendre la connexion (ERR_NETWORK_IO_SUSPENDED) pendant l'OCR.
  compress: false,
  // Tone.js est un gros paquet ESM : sans ça, Next 14 le découpe en un chunk
  // dynamique qui échoue à se charger (« Loading chunk …tone… failed »). Le
  // transpiler via le pipeline Next produit un bundle stable.
  transpilePackages: ["tone"],
};

export default nextConfig;
