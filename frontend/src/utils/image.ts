/** Réduit une image côté navigateur avant l'envoi : une photo de téléphone
 * fait souvent plus de 5 Mo, limite acceptée par le serveur. Le PNG garde la
 * transparence (logos) ; le JPEG est plus léger pour les photos. */
export async function shrinkImage(
  file: File, maxSide: number, format: "image/png" | "image/jpeg",
): Promise<Blob> {
  const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext("2d")!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  return new Promise((resolve, reject) =>
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("Image illisible"))), format, 0.9));
}
