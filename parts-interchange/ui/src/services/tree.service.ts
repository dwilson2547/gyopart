import { Injectable } from "@angular/core";
import { HttpClient, HttpParams } from "@angular/common/http";
import { environment } from "src/environments/environment";
import { YearResponse } from "src/interfaces/YearResponse";
import { MakeResponse } from "src/interfaces/MakeResponse";
import { ModelResponse } from "src/interfaces/ModelResponse";
import { TrimResponse } from "src/interfaces/TrimResponse";
import { EngineResponse } from "src/interfaces/EngineResponse";
import { CarResponse } from "src/interfaces/CarResponse";

@Injectable()
export class TreeService {
    constructor(private http: HttpClient) { }

    get_years() { 
        return this.http.get<YearResponse[]>(environment.api_url + '/tree/years')
    }

    get_makes(year_id: string) {
        let qp = new HttpParams();
        qp = qp.append('year_id', year_id)
        return this.http.get<MakeResponse[]>(environment.api_url + '/tree/makes', {params: qp})
    }

    get_models(year_id: string, make_id: string) {
        let qp = new HttpParams();
        qp = qp.append('year_id', year_id).append('make_id', make_id)

        return this.http.get<ModelResponse[]>(environment.api_url + '/tree/models', {params: qp})
    }

    get_trims(year_id: string, make_id: string, model_id: string) {
        let qp = new HttpParams();
        qp = qp.append('year_id', year_id).append('make_id', make_id).append('model_id', model_id)

        return this.http.get<TrimResponse[]>(environment.api_url + '/tree/trims', {params: qp})
    }

    get_engines(year_id: string, make_id: string, model_id: string, trim_id: string) {
        let qp = new HttpParams();
        qp = qp.append('year_id', year_id).append('make_id', make_id).append('model_id', model_id).append('trim_id', trim_id)

        return this.http.get<EngineResponse[]>(environment.api_url + '/tree/engines', {params: qp})
    }

    get_cars(year_id: string, make_id: string, model_id: string, trim_id: string, engine_id: string) {
        let qp = new HttpParams();
        qp = qp.append('year_id', year_id).append('make_id', make_id).append('model_id', model_id).append('trim_id', trim_id).append('engine_id', engine_id)

        return this.http.get<CarResponse[]>(environment.api_url + '/tree/cars', {params: qp})
    }

    get_parts(car_id: string) {
        let qp = new HttpParams();
        qp = qp.append('car_id', car_id)

        return this.http.get(environment.api_url + '/tree/parts', {params: qp})
    }
}






