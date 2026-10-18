import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Rate } from 'k6/metrics';

// Custom latency metrics
const identicalLatency = new Trend('latency_identical_payload');
const mixedLatency = new Trend('latency_mixed_payload');
const errorRate = new Rate('error_rate');

// Staged ramp up: 100 -> 1,000 -> 10,000 users
export const options = {
  stages: [
    { duration: '30s', target: 100 },    // Warmup to 100 concurrent users
    { duration: '1m',  target: 1000 },   // Scale to 1,000 concurrent users
    { duration: '2m',  target: 10000 },  // Peak at 10,000 concurrent users
    { duration: '30s', target: 0 },      // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<1500'],   // 95% under 1.5s
    error_rate: ['rate<0.05'],           // Error rate < 5% under 10k load
  },
};

const TRAIN_NO = '06030';

// 5 Consecutive Sundays for Train 06030
const SUNDAY_DATES = [
  '25-10-2026',
  '01-11-2026',
  '08-11-2026',
  '15-11-2026',
  '22-11-2026',
];

const TRAVEL_CLASSES = ['SL', '3A', '2A'];

// 23 Sequential Route Stations (Tirunelveli to Mettupalayam)
const ROUTE_STATIONS = [
  'TEN',  // Tirunelveli (Origin)
  'SMD',  // Cheranmahadevi
  'KIC',  // Kallidaikurichi
  'ASD',  // Ambasamudram
  'KKY',  // Kilakadaiyam
  'PCM',  // Pavurchatram
  'TSI',  // Tenkasi Junction
  'KDNL', // Kadayanallur
  'SNKL', // Sankarankovil
  'RJPM', // Rajapalayam
  'SVPR', // Srivilliputtur
  'SVKS', // Sivakasi
  'VPT',  // Virudhunagar Junction
  'MDU',  // Madurai Junction
  'DG',   // Dindigul Junction
  'ODC',  // Oddanchatram
  'PLNI', // Palani
  'UDT',  // Udumalaipettai
  'POY',  // Pollachi Junction
  'KKN',  // Kinathukadavu
  'PTJ',  // Podanur Junction
  'CBE',  // Coimbatore Junction
  'MTP',  // Mettupalayam (Destination)
];

function getRandomForwardRoute() {
  const i = Math.floor(Math.random() * (ROUTE_STATIONS.length - 1));
  const j = Math.floor(Math.random() * (ROUTE_STATIONS.length - 1 - i)) + i + 1;
  return { src: ROUTE_STATIONS[i], dst: ROUTE_STATIONS[j] };
}

export default function () {
  // 50% traffic identical hot query (Singleflight coalescing test)
  // 50% traffic diverse multi-station query (253 route pairs, 5 Sundays, 3 classes)
  const isIdentical = Math.random() < 0.5;

  let payloadObj;
  if (isIdentical) {
    payloadObj = {
      trainNo: TRAIN_NO,
      source: 'TEN',
      destination: 'MTP',
      travelClass: 'SL',
      date: '25-10-2026',
      quota: 'GN',
    };
  } else {
    const route = getRandomForwardRoute();
    const cls = TRAVEL_CLASSES[Math.floor(Math.random() * TRAVEL_CLASSES.length)];
    const date = SUNDAY_DATES[Math.floor(Math.random() * SUNDAY_DATES.length)];
    payloadObj = {
      trainNo: TRAIN_NO,
      source: route.src,
      destination: route.dst,
      travelClass: cls,
      date: date,
      quota: 'GN',
    };
  }

  const payload = JSON.stringify(payloadObj);
  const params = {
    headers: {
      'Content-Type': 'application/json',
    },
    timeout: '15s',
  };

  const res = http.post('http://127.0.0.1:8005/api/v1/trains/availability', payload, params);

  const isSuccess = check(res, {
    'status is 200': (r) => r.status === 200,
  });

  errorRate.add(!isSuccess);

  if (isIdentical) {
    identicalLatency.add(res.timings.duration);
  } else {
    mixedLatency.add(res.timings.duration);
  }

  sleep(0.05);
}
