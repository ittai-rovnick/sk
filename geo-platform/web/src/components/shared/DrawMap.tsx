import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import MapboxDraw from "@mapbox/mapbox-gl-draw";
import "maplibre-gl/dist/maplibre-gl.css";
import "@mapbox/mapbox-gl-draw/dist/mapbox-gl-draw.css";

export interface DrawMapProps {
  /** Initial GeoJSON to load into the editor */
  initialFeatures?: GeoJSON.Feature[];
  /** Called whenever features are created, updated, or deleted */
  onChange?: (features: GeoJSON.Feature[]) => void;
  style?: React.CSSProperties;
}

export function DrawMap({ initialFeatures, onChange, style }: DrawMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const drawRef = useRef<MapboxDraw | null>(null);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: {
        version: 8,
        sources: {
          osm: {
            type: "raster",
            tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: "© OpenStreetMap contributors",
          },
        },
        layers: [{ id: "osm", type: "raster", source: "osm" }],
      },
      center: [35.2, 31.8],
      zoom: 7,
    });

    const draw = new MapboxDraw({
      displayControlsDefault: false,
      controls: {
        point: true,
        line_string: true,
        polygon: true,
        trash: true,
        combine_features: false,
        uncombine_features: false,
      },
    });

    // MapboxDraw expects the map to have a certain interface — cast is needed
    // because maplibregl and mapboxgl types differ slightly but are compatible
    map.addControl(new maplibregl.NavigationControl(), "top-right");
    map.addControl(draw as unknown as maplibregl.IControl, "top-left");

    map.on("load", () => {
      if (initialFeatures && initialFeatures.length > 0) {
        draw.add({ type: "FeatureCollection", features: initialFeatures });

        // Fit to initial features
        const coords: [number, number][] = [];
        initialFeatures.forEach((f) => {
          if (f.geometry.type === "Point") {
            coords.push(f.geometry.coordinates as [number, number]);
          } else if (f.geometry.type === "LineString") {
            coords.push(...(f.geometry.coordinates as [number, number][]));
          } else if (f.geometry.type === "Polygon") {
            coords.push(...(f.geometry.coordinates[0] as [number, number][]));
          }
        });
        if (coords.length > 0) {
          const lngs = coords.map((c) => c[0]);
          const lats = coords.map((c) => c[1]);
          map.fitBounds(
            [[Math.min(...lngs), Math.min(...lats)], [Math.max(...lngs), Math.max(...lats)]],
            { padding: 60, maxZoom: 14 }
          );
        }
      }
    });

    function emitChange() {
      if (onChange) {
        onChange(draw.getAll().features as GeoJSON.Feature[]);
      }
    }

    map.on("draw.create", emitChange);
    map.on("draw.update", emitChange);
    map.on("draw.delete", emitChange);

    mapRef.current = map;
    drawRef.current = draw;

    return () => {
      map.remove();
      mapRef.current = null;
      drawRef.current = null;
    };
  }, []);

  return (
    <div
      ref={containerRef}
      style={{ width: "100%", height: 480, borderRadius: 8, overflow: "hidden", ...style }}
    />
  );
}
