import { Component, OnInit } from '@angular/core';
import { Message, MessageQueues, MessageService } from 'src/services/message.service';
import { TreeService } from 'src/services/tree.service';
import { Select2Data, Select2Option, Select2UpdateEvent } from 'ng-select2-component';
import { CarResponse } from 'src/interfaces/CarResponse';
import { LocalStorage } from '../constants/localstorage';
import { LocalStoreCarList, LocalStoreCar } from 'src/interfaces/LocalStoreCars';
import { zip } from 'rxjs';

@Component({
  selector: 'app-car-picker-v2',
  templateUrl: './car-picker-v2.component.html',
  styleUrls: ['./car-picker-v2.component.scss'],
  providers: [TreeService]
})
export class CarPickerV2Component implements OnInit {

  ddlYear: string | null = null;
  ddlMake: string | null = null;
  ddlModel: string | null = null;
  ddlTrim: string | null = null;
  ddlEngine: string | null = null;

  s2_years: Select2Option[] = [];
  s2_makes: Select2Option[] = [];
  s2_models: Select2Option[] = [];
  s2_trims: Select2Option[] = [];
  s2_engines: Select2Option[] = [];
  s2_car: CarResponse | null = null;

  selected_car: LocalStoreCar = {
    year: "",
    make: "",
    model: "",
    trim: "",
    engine: "",
    id: -1
  }

  constructor(private treeService: TreeService, private messageService: MessageService) { }

  ngOnInit(): void {
    this.load();
  }

  load() {
    this.treeService.get_years().subscribe((data) => {
      this.s2_years = [];
      data.forEach(element => {
        this.s2_years.push({ value: element.id, label: element.name })
      });
      this.ddlYear = null;
      this.ddlMake = null;
      this.ddlModel = null;
      this.ddlTrim = null;
      this.ddlEngine = null;
      this.s2_makes = [];
      this.s2_models = [];
      this.s2_engines = [];
      this.s2_trims = [];
    })
  }

  set_year(event: Select2UpdateEvent<string>) {
    if (event.value) {
      console.log(this.s2_years)
      this.selected_car.year = event.options[0].label;
      this.ddlYear = event.value;
      this.treeService.get_makes(this.ddlYear).subscribe((data) => {
        this.s2_makes = [];
        data.forEach(element => {
          this.s2_makes.push({ value: element.id, label: element.name })
        })
        this.ddlMake = null;
        this.ddlModel = null;
        this.ddlTrim = null;
        this.ddlEngine = null;
        this.s2_models = [];
        this.s2_engines = [];
        this.s2_trims = [];
      })
    }
  }
  
  set_make(event: Select2UpdateEvent<string>) {
    if (this.ddlYear && event.value) {
      this.ddlMake = event.value;
      this.treeService.get_models(this.ddlYear, this.ddlMake).subscribe((data) => {
        this.s2_models = [];
        data.forEach(element => {
          this.s2_models.push({ value: element.id, label: element.name })
        })
        this.ddlModel = null;
        this.ddlTrim = null;
        this.ddlEngine = null;
        this.s2_engines = [];
        this.s2_trims = [];
      })
    }

  }

  set_model(event: Select2UpdateEvent<string>) {
    if (this.ddlYear && this.ddlMake && event.value) {
      this.ddlModel = event.value;
      this.treeService.get_trims(this.ddlYear, this.ddlMake, this.ddlModel).subscribe((data) => {
        this.s2_trims = [];
        data.forEach(element => {
          this.s2_trims.push({ value: element.id, label: element.name })
        })
        this.ddlTrim = null;
        this.ddlEngine = null;
        this.s2_engines = [];
      })
    }

  }

  set_trim(event: Select2UpdateEvent<string>) {
    if (this.ddlYear && this.ddlMake && this.ddlModel && event.value) {
      this.ddlTrim = event.value;
      this.treeService.get_engines(this.ddlYear, this.ddlMake, this.ddlModel, this.ddlTrim).subscribe((data) => {
        this.s2_engines = [];
        data.forEach(element => {
          this.s2_engines.push({ value: element.id, label: element.name })
        })
        this.ddlEngine = null;
      })
    }
  }

  set_engine(event: Select2UpdateEvent<string>) {
    if (this.ddlYear && this.ddlMake && this.ddlModel && this.ddlTrim && event.value) {
      this.ddlEngine = event.value;
      this.treeService.get_cars(this.ddlYear, this.ddlMake, this.ddlModel, this.ddlTrim, this.ddlEngine).subscribe((data) => {
        this.s2_car = data[0];
        console.log(data);
        let msg = new Message(MessageQueues.CAR_PICKER_QUEUE, this.s2_car);
        this.messageService.sendMessage(msg);
      })
    }
  }

  save_car() {
    if (this.s2_car) {
      let year = this.s2_years.find(x => x.value == this.ddlYear)?.label;
      let make = this.s2_makes.find(x => x.value == this.ddlMake)?.label;
      let model = this.s2_models.find(x => x.value == this.ddlModel)?.label;
      let trim = this.s2_trims.find(x => x.value == this.ddlTrim)?.label;
      let engine = this.s2_engines.find(x => x.value == this.ddlEngine)?.label;

      let val = localStorage.getItem(LocalStorage.ClientCars);
      if (val) {
        let clientCars: LocalStoreCar[] = JSON.parse(val);
        let res = clientCars.find(x => x.id == this.s2_car?.id)
        if (!res && year && make && model && trim && engine) {
          clientCars.push({year: year, make: make, model: model, trim: trim, engine: engine, id: this.s2_car.id});
          localStorage.setItem(LocalStorage.ClientCars, JSON.stringify(clientCars));
        }
      } else {
        let clientCars = [{year: year, make: make, model: model, trim: trim, engine: engine, id: this.s2_car.id}];
        localStorage.setItem(LocalStorage.ClientCars, JSON.stringify(clientCars));
      }
    }
  }
}
